#!/usr/bin/env python3

import os
import sys
import json
import argparse
import subprocess
import platform
from pathlib import Path
from .video_processor import VideoProcessor
from .key_moments import KeyMomentsExtractor
from .web_generator import WebGenerator

WHISPER_DEVICE_BY_PLATFORM = {
    "Darwin": "mps",
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
        print("pip install -r requirements.txt")
        return False

def check_api_key():
    """Check if the default Anthropic API key is available."""
    if os.environ.get('ANTHROPIC_API_KEY'):
        return True
    print("Error: ANTHROPIC_API_KEY environment variable is not set")
    return False

def get_api_config(args):
    """Determine API provider and key from command line args and environment."""
    if getattr(args, "apple", False):
        return "apple", None
    if args.anthropic is not None:  # --anthropic was used
        provider = "anthropic"
        key = args.anthropic if args.anthropic else os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            print("Error: Anthropic API key required")
            print("Provide via --anthropic [key] or set ANTHROPIC_API_KEY environment variable")
            return None, None
    elif args.openai is not None:  # --openai was used
        provider = "openai"
        key = args.openai if args.openai else os.environ.get('OPENAI_API_KEY')
        if not key:
            print("Error: OpenAI API key required")
            print("Provide via --openai [key] or set OPENAI_API_KEY environment variable")
            return None, None
    else:
        print("Error: Must specify --anthropic, --openai, or --apple")
        return None, None
    
    return provider, key

def create_transcriber(audio_path: str, transcriber_name: str = "whisper", device_id: str = None):
    """Create the configured audio transcriber."""
    if transcriber_name == "whisper":
        from .transcriber import Transcriber

        return Transcriber(audio_path, device_id=device_id or default_whisper_device_id())
    if transcriber_name == "dictation":
        from .transcriber_apple_dictation import AppleDictationTranscriber

        return AppleDictationTranscriber(audio_path)
    raise ValueError("transcriber_name must be 'whisper' or 'dictation'")

def transcriber_for_provider(api_provider: str):
    """Map the selected running mode to its transcription backend."""
    if api_provider == "apple":
        return "dictation"
    if api_provider in ("openai", "anthropic"):
        return "whisper"
    raise ValueError("api_provider must be 'anthropic', 'openai', or 'apple'")

def process_video(video_path: str, output_dir: str = "output", device_id: str = None, skip_to: str = None,
                 api_provider: str = None, api_key: str = None):
    """
    Main processing pipeline for video indexing.
    
    Args:
        video_path: Path to the input video file
        output_dir: Directory to store intermediate files
        device_id: Device ID for Whisper inference ("0" for CPU/CUDA, "mps" for Darwin)
        skip_to: Stage to skip to ('transcribe', 'analyze', or 'generate')
        api_provider: Running mode. Apple uses Apple Dictation; OpenAI/Anthropic use Whisper.
    """
    os.makedirs(output_dir, exist_ok=True)
    print("\nProcessing video...")
    api_provider = api_provider or "anthropic"
    transcriber_name = transcriber_for_provider(api_provider)
    
    audio_path = os.path.join(output_dir, f"{Path(video_path).stem}_audio.wav")
    transcript_path = os.path.join(output_dir, "audio_transcript.json")
    subtitle_path = os.path.join(output_dir, "audio_subtitles.srt")
    analysis_path = os.path.join(output_dir, "meeting_analysis.json")

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
        transcriber = create_transcriber(audio_path, transcriber_name, device_id)
        transcriber.transcribe(transcript_path, subtitle_path)
    
    if not skip_to or skip_to in ['analyze', 'transcribe']:
        # Extract topics, key moments, and takeaways from the subtitles
        print("3. Analyzing content...")
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
        
        try:
            key_extractor = KeyMomentsExtractor(subtitle_path, api_provider=api_provider, api_key=api_key)
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
        with open(analysis_path, "w") as f:
            json.dump(analysis, f, indent=2)
        print(f"   Analysis saved to: {analysis_path}")
    
    if not skip_to or skip_to in ['generate', 'analyze', 'transcribe']:
        # Generate webpage with analysis and video
        print("4. Generating webpage...")
        if not os.path.exists(analysis_path):
            raise FileNotFoundError(f"Analysis file not found: {analysis_path}")
        
        video_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        
        web_generator = WebGenerator(analysis_path, video_path, transcript_path)
        output_webpage_path = web_generator.generate(output_dir, f"{video_name}_summary.html")
        
        webpage_path = os.path.join(video_dir, f"{video_name}_summary.html")
        with open(output_webpage_path, 'r') as src, open(webpage_path, 'w') as dst:
            dst.write(src.read())
        
        print(f"   Webpage saved to:")
        print(f"   {webpage_path}")
    
    print("\nProcessing complete!")
    print(f"\nOpen {webpage_path} in your browser to view the meeting summary.")

def main():
    parser = argparse.ArgumentParser(description="Process a video file to extract key moments and takeaways")
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--output-dir", default="output", help="Directory to store intermediate files")
    parser.add_argument("--device-id", help='Override Whisper device ID ("mps" on Darwin by default, "0" on Windows/Linux)')
    parser.add_argument("--skipto", choices=['transcribe', 'analyze', 'generate'], dest="skip_to",
                       help="Skip to a specific stage (transcribe, analyze, or generate)")
    
    # API provider selection - mutually exclusive
    api_group = parser.add_mutually_exclusive_group(required=True)
    api_group.add_argument("--anthropic", nargs='?', const='', 
                          help="Use Anthropic Claude (optional key, falls back to ANTHROPIC_API_KEY env var)")
    api_group.add_argument("--openai", nargs='?', const='',
                          help="Use OpenAI GPT (optional key, falls back to OPENAI_API_KEY env var)")
    api_group.add_argument("--apple", action="store_true",
                          help="Use Apple Foundation Models on this Mac (no API key required)")
    
    args = parser.parse_args()
    load_env_file()
    
    # Check basic dependencies first
    if not all([check_ffmpeg(), check_python_dependencies()]):
        sys.exit(1)
    
    # Get API configuration
    api_provider, api_key = get_api_config(args)
    if not api_provider:
        sys.exit(1)
    
    process_video(args.video_path, args.output_dir, args.device_id, args.skip_to,
                 api_provider, api_key)

if __name__ == "__main__":
    main()
