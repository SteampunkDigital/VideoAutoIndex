#!/usr/bin/env python3

import os
import sys
import argparse
import subprocess
from pathlib import Path

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
        import faster_whisper
        return True
    except ImportError as e:
        missing_package = str(e).split("'")[1]
        print(f"Error: Required Python package '{missing_package}' is not installed")
        print("\nTo install required packages:")
        print("pip install -r requirements.txt")
        return False

def process_video(video_path: str, output_dir: str = "output"):
    """
    Main processing pipeline for video indexing.
    
    Args:
        video_path: Path to the input video file
        output_dir: Directory to store all output files
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # TODO: Implement each step:
    # 1. Extract audio
    # audio_path = extract_audio(video_path, output_dir)
    
    # 2. Transcribe audio
    # subtitle_path = transcribe_audio(audio_path, output_dir)
    
    # 3. Extract key moments
    # key_moments = extract_key_moments(subtitle_path)
    
    # 4. Generate takeaways
    # takeaways = extract_takeaways(key_moments)
    
    # 5. Add chapters to video
    # chaptered_video = add_video_chapters(video_path, key_moments, output_dir)
    
    # 6. Generate webpage
    # generate_webpage(key_moments, takeaways, chaptered_video, output_dir)

def main():
    # Check dependencies before proceeding
    if not check_ffmpeg() or not check_python_dependencies():
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Process a video file to extract key moments and takeaways")
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--output-dir", default="output", help="Directory to store output files")
    
    args = parser.parse_args()
    process_video(args.video_path, args.output_dir)

if __name__ == "__main__":
    main()
