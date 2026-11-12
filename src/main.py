#!/usr/bin/env python3

import os
import sys
import json
import argparse
import subprocess
import platform
import shutil
from pathlib import Path
from .video_processor import VideoProcessor
from .key_moments import KeyMomentsExtractor, DEFAULT_OPENAI_MODEL, DEFAULT_ANTHROPIC_MODEL
from .web_generator import WebGenerator

WHISPER_DEVICE_BY_PLATFORM = {
    "Darwin": "mps",
}
WHISPER_LANGUAGE_BY_TRANSCRIPTION_LANGUAGE = {
    "en": "en",
    "ja": "ja",
}
APPLE_LOCALE_BY_TRANSCRIPTION_LANGUAGE = {
    "en": "en-US",
    "ja": "ja-JP",
}

def load_env_file(env_path: str = ".env"):
    """Load simple KEY=value entries from a .env file without overriding the shell."""
    path = Path(env_path)
    if not path.exists():
        return

    with path.open() as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

def default_whisper_device_id():
    """Return the default insanely-fast-whisper device for this platform."""
    return WHISPER_DEVICE_BY_PLATFORM.get(platform.system(), "0")

def check_ffmpeg():
    """Check if ffmpeg is installed and accessible."""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("Error: ffmpeg is not installed or not found in PATH")
        print("\nTo install ffmpeg:")
        print("- On macOS: brew install ffmpeg")
        print("- On Ubuntu/Debian: sudo apt-get install ffmpeg")
        print("- On Windows: Download from https://ffmpeg.org/download.html")
        return False

def check_python_dependencies():
    """Check if required Python packages are installed."""
    try:
        import ffmpeg
        import anthropic
        import openai
        import flask
        return True
    except ImportError as e:
        missing_package = str(e).split("'")[1]
        print(f"Error: Required Python package '{missing_package}' is not installed")
        print("\nTo install required packages:")
        print("pip install -e .")
        return False

def api_key_for_provider(provider):
    """Resolve credentials for one stage, independently of the other stage."""
    variable = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider)
    if variable is None:
        return None
    key = os.environ.get(variable)
    if not key:
        raise ValueError(f"{variable} is required for {provider}")
    return key

def whisper_language_for_transcription_language(transcription_language: str) -> str:
    """Return the Whisper language code for a supported transcription language."""
    return WHISPER_LANGUAGE_BY_TRANSCRIPTION_LANGUAGE[transcription_language]

def apple_locale_for_transcription_language(transcription_language: str) -> str:
    """Return the Apple Speech locale for a supported transcription language."""
    return APPLE_LOCALE_BY_TRANSCRIPTION_LANGUAGE[transcription_language]

def create_transcriber(
    audio_path: str,
    transcriber_name: str = "whisper",
    device_id: str = None,
    transcription_language: str = "en",
    api_key: str = None,
    model_name: str = None,
):
    """Create the configured audio transcriber."""
    if transcriber_name == "whisper":
        from .transcriber import Transcriber

        return Transcriber(
            audio_path,
            device_id=device_id or default_whisper_device_id(),
            language=whisper_language_for_transcription_language(transcription_language),
            **({"model_name": model_name} if model_name else {}),
        )
    if transcriber_name in ("apple", "apple_speech"):
        if model_name:
            raise ValueError("Apple transcription does not support a model override")
        from .transcriber_apple_speech import AppleSpeechTranscriber

        compare_locale = "en-US" if transcription_language == "ja" else None
        return AppleSpeechTranscriber(
            audio_path,
            locale=apple_locale_for_transcription_language(transcription_language),
            compare_locale=compare_locale,
        )
    if transcriber_name == "openai":
        from .transcriber_openai import OpenAITranscriber, DEFAULT_TRANSCRIPTION_MODEL

        return OpenAITranscriber(audio_path, api_key=api_key,
                                 model_name=model_name or DEFAULT_TRANSCRIPTION_MODEL,
                                 language=transcription_language)
    if transcriber_name == "speechcpp":
        from .transcriber_speechcpp import SpeechCppTranscriber

        return SpeechCppTranscriber(audio_path, model_name=model_name, language=transcription_language)
    raise ValueError("transcriber_name must be 'whisper', 'apple', 'openai', or 'speechcpp'")

def process_video(video_path: str, output_dir: str = "output", device_id: str = None, skip_to: str = None,
                 api_provider: str = None, api_key: str = None, transcription_language: str = "en",
                 transcriber_name: str = "whisper", transcribe_api_key: str = None,
                 transcribe_model: str = None, summarize_model: str = None, feedback_path: str = None):
    """
    Main processing pipeline for video indexing.
    
    Args:
        video_path: Path to the input video file
        output_dir: Directory to store intermediate files
        device_id: Device ID for Whisper inference ("0" for CPU/CUDA, "mps" for Darwin)
        skip_to: Stage to skip to ('transcribe', 'analyze', or 'generate')
        api_provider: Provider for summarization, independent of transcription.
        transcription_language: Native transcription language ("en" or "ja")
    """
    os.makedirs(output_dir, exist_ok=True)
    print("\nProcessing video...")
    api_provider = api_provider or "anthropic"
    
    audio_path = os.path.join(output_dir, f"{Path(video_path).stem}_audio.wav")
    transcript_path = os.path.join(output_dir, "audio_transcript.json")
    subtitle_path = os.path.join(output_dir, "audio_subtitles.srt")
    analysis_path = os.path.join(output_dir, "meeting_analysis.json")
    if feedback_path:
        if skip_to != 'analyze':
            raise ValueError('--feedback requires --skipto analyze to use the existing transcript and refresh its summary')
        from .transcript_feedback import import_feedback

        transcript_path, subtitle_path = import_feedback(output_dir, feedback_path, Path(video_path).name)
        analysis_path = os.path.join(output_dir, 'meeting_analysis.reviewed.json')
        print('   Applied confirmed feedback to separate reviewed transcript/subtitle files')

    if not skip_to:
        # Extract audio from the video file
        print("1. Extracting audio...")
        processor = VideoProcessor(video_path)
        audio_path = processor.extract_audio(output_dir)

    if not skip_to or skip_to == 'transcribe':
        # Transcribe the extracted audio file
        print("2. Transcribing audio...")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        transcriber = create_transcriber(
            audio_path,
            transcriber_name,
            device_id,
            transcription_language,
            api_key=transcribe_api_key,
            model_name=transcribe_model,
        )
        transcriber.transcribe(transcript_path, subtitle_path)
    
    if not skip_to or skip_to in ['analyze', 'transcribe']:
        # Extract topics, key moments, and takeaways from the subtitles
        print("3. Analyzing content...")
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
        
        try:
            key_extractor = KeyMomentsExtractor(subtitle_path, api_provider=api_provider, api_key=api_key,
                                               model_name=summarize_model)
            analysis = key_extractor.extract_key_moments()
        except Exception as e:
            print(f"\nError during content analysis: {str(e)}")
            print("\nTroubleshooting tips:")
            if "rate limit" in str(e).lower() or "quota" in str(e).lower():
                print("- Check your API usage and billing at your provider's dashboard")
                print("- Consider upgrading your API plan if you've exceeded limits")
                print("- Wait a few minutes before retrying if you hit rate limits")
            elif "authentication" in str(e).lower():
                print("- Verify your API key is correct and active")
                print("- Check that your API key has the necessary permissions")
            elif "connection" in str(e).lower():
                print("- Check your internet connection")
                print("- Verify that your firewall/proxy allows API access")
            else:
                print("- Try again in a few minutes")
                print("- Check the API provider's status page for outages")
            sys.exit(1)
        
        # Save analysis to a JSON file
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2)
        print(f"   Analysis saved to: {analysis_path}")
    
    if not skip_to or skip_to in ['generate', 'analyze', 'transcribe']:
        # Generate webpage with analysis and video
        print("4. Generating webpage...")
        if not os.path.exists(analysis_path):
            raise FileNotFoundError(f"Analysis file not found: {analysis_path}")
        
        video_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        if feedback_path:
            video_name += '_reviewed'
        
        web_generator = WebGenerator(analysis_path, video_path, transcript_path)
        output_webpage_path = web_generator.generate(output_dir, f"{video_name}_summary.html")
        
        webpage_path = os.path.join(video_dir, f"{video_name}_summary.html")
        if Path(output_webpage_path).resolve() != Path(webpage_path).resolve():
            shutil.copyfile(output_webpage_path, webpage_path)
        
        print(f"   Webpage saved to:")
        print(f"   {webpage_path}")
    
    print("\nProcessing complete!")
    print(f"\nOpen {webpage_path} in your browser to view the meeting summary.")

def build_parser():
    parser = argparse.ArgumentParser(description="Process a video file to extract key moments and takeaways")
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--output-dir", default="output", help="Directory to store intermediate files")
    parser.add_argument("--device-id", help='Override Whisper device ID ("mps" on Darwin by default, "0" on Windows/Linux)')
    parser.add_argument("--transcription-language", choices=["en", "ja"], default="en",
                       help="Native transcription language: en for English, ja for Japanese")
    parser.add_argument("--skipto", choices=['transcribe', 'analyze', 'generate'], dest="skip_to",
                       help="Skip to a specific stage (transcribe, analyze, or generate)")
    
    parser.add_argument("--transcribe", choices=["whisper", "apple", "openai", "speechcpp"], default="whisper",
                        help="Speech recognition provider (default: whisper)")
    parser.add_argument("--summarize", choices=["anthropic", "apple", "openai"],
                        help="Provider for topics, key moments, and takeaways (required unless --skipto generate)")
    parser.add_argument("--transcribe-model", help="Transcription model override (Whisper, OpenAI, or speech.cpp)")
    parser.add_argument("--summarize-model", help="Summarization model override (Anthropic or OpenAI)")
    parser.add_argument('--feedback', help='Apply exported correction JSON to an existing transcript (requires --skipto analyze)')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    load_env_file()
    transcribing = args.skip_to in (None, "transcribe")
    summarizing = args.skip_to != "generate"
    transcribe_key = summarize_key = None
    try:
        if args.feedback and args.skip_to != 'analyze':
            raise ValueError('--feedback requires --skipto analyze')
        if transcribing:
            if args.transcribe == "apple" and args.transcribe_model:
                raise ValueError("--transcribe-model is not supported with --transcribe apple")
            if args.transcribe == "openai":
                from .transcriber_openai import validate_model, DEFAULT_TRANSCRIPTION_MODEL
                validate_model(args.transcribe_model or DEFAULT_TRANSCRIPTION_MODEL)
            if args.transcribe == "speechcpp":
                from .transcriber_speechcpp import validate_model, DEFAULT_MODELS
                validate_model(args.transcribe_model or DEFAULT_MODELS[args.transcription_language],
                               args.transcription_language)
            transcribe_key = api_key_for_provider(args.transcribe)
        if summarizing:
            if not args.summarize:
                raise ValueError("--summarize is required unless --skipto generate is used")
            if args.summarize == "apple" and args.summarize_model:
                raise ValueError("--summarize-model is not supported with --summarize apple")
            summarize_key = api_key_for_provider(args.summarize)
    except ValueError as error:
        parser.error(str(error))

    if not check_python_dependencies() or (transcribing and not check_ffmpeg()):
        sys.exit(1)
    if transcribing:
        defaults = {"whisper": "openai/whisper-large-v3-turbo", "apple": "SpeechTranscriber",
                    "openai": "gpt-4o-transcribe-diarize"}
        if args.transcribe == "speechcpp":
            from .transcriber_speechcpp import DEFAULT_MODELS
            defaults["speechcpp"] = DEFAULT_MODELS[args.transcription_language]
        print(f"Transcription: {args.transcribe} / {args.transcribe_model or defaults[args.transcribe]}")
    if summarizing:
        defaults = {"anthropic": DEFAULT_ANTHROPIC_MODEL, "openai": DEFAULT_OPENAI_MODEL,
                    "apple": "Foundation Models (automatic)"}
        print(f"Summarization: {args.summarize} / {args.summarize_model or defaults[args.summarize]}")
    process_video(
        args.video_path, args.output_dir, args.device_id, args.skip_to,
        api_provider=args.summarize, api_key=summarize_key,
        transcription_language=args.transcription_language,
        transcriber_name=args.transcribe, transcribe_api_key=transcribe_key,
        transcribe_model=args.transcribe_model, summarize_model=args.summarize_model,
        feedback_path=args.feedback,
    )

if __name__ == "__main__":
    main()
