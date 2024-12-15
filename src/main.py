#!/usr/bin/env python3

import os
import sys
import argparse
import subprocess
from pathlib import Path
from video_processor import VideoProcessor
from transcriber import Transcriber
from key_moments import KeyMomentsExtractor

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
        import requests  # Required for ollama API calls
        return True
    except ImportError as e:
        missing_package = str(e).split("'")[1]
        print(f"Error: Required Python package '{missing_package}' is not installed")
        print("\nTo install required packages:")
        print("pip install -r requirements.txt")
        return False

def check_ollama():
    """Check if ollama is running and accessible."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/version")
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        print("Error: Ollama is not running or not accessible at http://localhost:11434")
        print("\nTo start ollama:")
        print("1. Make sure ollama is installed (https://ollama.ai)")
        print("2. Run 'ollama serve' in a terminal")
        print("3. In another terminal, run 'ollama pull mistral' to download the required model")
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
    
    # Extract audio from the video file
    processor = VideoProcessor(video_path)
    audio_path = processor.extract_audio(output_dir)

    # Transcribe the extracted audio file
    transcriber = Transcriber(audio_path)
    subtitle_path = transcriber.transcribe(output_dir)
    
    # Extract key moments from the subtitles
    key_extractor = KeyMomentsExtractor(subtitle_path)
    key_moments = key_extractor.extract_key_moments()
    
    # TODO: Implement remaining steps:
    # 4. Generate takeaways
    # takeaways = extract_takeaways(key_moments)
    
    # 5. Add chapters to video
    # chaptered_video = processor.add_chapters(key_moments, output_dir)
    
    # 6. Generate webpage
    # generate_webpage(key_moments, takeaways, chaptered_video, output_dir)

def main():
    # Check all dependencies before proceeding
    if not all([
        check_ffmpeg(),
        check_python_dependencies(),
        check_ollama()
    ]):
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Process a video file to extract key moments and takeaways")
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--output-dir", default="output", help="Directory to store output files")
    
    args = parser.parse_args()
    process_video(args.video_path, args.output_dir)

if __name__ == "__main__":
    main()
