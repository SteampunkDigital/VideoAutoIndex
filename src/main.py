#!/usr/bin/env python3

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from .video_processor import VideoProcessor
from .transcriber import Transcriber
from .key_moments import KeyMomentsExtractor
from .web_generator import WebGenerator

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
        import flask
        return True
    except ImportError as e:
        missing_package = str(e).split("'")[1]
        print(f"Error: Required Python package '{missing_package}' is not installed")
        print("\nTo install required packages:")
        print("pip install -r requirements.txt")
        return False

def check_api_key():
    """Check if Anthropic API key is set."""
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("Error: ANTHROPIC_API_KEY environment variable is not set")
        print("\nTo set the API key:")
        print("export ANTHROPIC_API_KEY='your-api-key'")
        return False
    return True

def process_video(video_path: str, output_dir: str = "output", device_id: str = None):
    """
    Main processing pipeline for video indexing.
    
    Args:
        video_path: Path to the input video file
        output_dir: Directory to store intermediate files
        device_id: Device ID for inference ("0" for CPU/CUDA, "mps" for Apple Silicon)
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    print("\nProcessing video...")
    
    # Extract audio from the video file
    print("1. Extracting audio...")
    processor = VideoProcessor(video_path)
    audio_path = processor.extract_audio(output_dir)

    # Transcribe the extracted audio file
    print("2. Transcribing audio...")
    transcriber = Transcriber(audio_path, device_id=device_id)
    transcript_path = os.path.join(output_dir, "audio_transcript.json")
    subtitle_path = os.path.join(output_dir, "audio_subtitles.srt")
    transcriber.transcribe(transcript_path, subtitle_path)
    
    # Extract topics, key moments, and takeaways from the subtitles
    print("3. Analyzing content...")
    key_extractor = KeyMomentsExtractor(subtitle_path)
    analysis = key_extractor.extract_key_moments()
    
    # Save analysis to a JSON file
    analysis_path = os.path.join(output_dir, "meeting_analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"   Analysis saved to: {analysis_path}")
    
    # Generate webpage with analysis and video
    print("4. Generating webpage...")
    # Get the directory and base name of the input video
    video_dir = os.path.dirname(video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    
    web_generator = WebGenerator(analysis_path, video_path)
    
    # Generate in output directory
    output_webpage_path = web_generator.generate(output_dir, f"{video_name}_summary.html")
    
    # Copy to video directory for proper video path resolution
    webpage_path = os.path.join(video_dir, f"{video_name}_summary.html")
    with open(output_webpage_path, 'r') as src, open(webpage_path, 'w') as dst:
        dst.write(src.read())
    
    print(f"   Webpage saved to:")
    print(f"   {webpage_path}")
    
    print("\nProcessing complete!")
    print(f"\nOpen {webpage_path} in your browser to view the meeting summary.")

def main():
    # Check all dependencies before proceeding
    if not all([
        check_ffmpeg(),
        check_python_dependencies(),
        check_api_key()
    ]):
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Process a video file to extract key moments and takeaways")
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--output-dir", default="output", help="Directory to store intermediate files")
    parser.add_argument("--device-id", help='Device ID for inference ("0" for CPU/CUDA, "mps" for Apple Silicon)')
    
    args = parser.parse_args()
    process_video(args.video_path, args.output_dir, args.device_id)

if __name__ == "__main__":
    main()
