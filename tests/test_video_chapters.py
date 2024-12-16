import os
import sys
import json

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.video_processor import VideoProcessor

def main():
    # Get the paths to test files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(script_dir, "..", "videos", "sample.mp4")
    analysis_path = os.path.join(script_dir, "sample_meeting_analysis.json")
    
    print(f"Using video: {video_path}")
    print(f"Using analysis: {analysis_path}")
    
    # Load the analysis JSON
    with open(analysis_path, 'r') as f:
        analysis = json.load(f)
    
    # Create video processor
    processor = VideoProcessor(video_path)
    
    # Add chapters
    print("\nAdding chapters to video...")
    output_path = processor.add_chapters(analysis, "output")
    
    print(f"\nProcessed video saved to: {output_path}")

if __name__ == "__main__":
    main()
