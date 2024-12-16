import os
import sys
import json

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.key_moments import KeyMomentsExtractor

def main():
    # Get the path to the sample transcript
    script_dir = os.path.dirname(os.path.abspath(__file__))
    transcript_path = os.path.join(script_dir, "do-not-share-sample_audio.srt")
    
    print(f"Using transcript: {transcript_path}")
    
    # Create extractor
    extractor = KeyMomentsExtractor(transcript_path)
    
    # Extract key moments
    print("\nExtracting key moments...")
    analysis = extractor.extract_key_moments()
    
    # Print results
    print("\nAnalysis results:")
    print(json.dumps(analysis, indent=2))

if __name__ == "__main__":
    main()
