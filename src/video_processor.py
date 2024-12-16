import ffmpeg
import os
from pathlib import Path
from typing import List, Dict

class VideoProcessor:
    def __init__(self, video_path: str):
        """
        Initialize the video processor.
        
        Args:
            video_path: Path to the input video file
        """
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

    def extract_audio(self, output_dir: str) -> str:
        """
        Extract audio from the video file.
        
        Args:
            output_dir: Directory to save the extracted audio
            
        Returns:
            Path to the extracted audio file
        """
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{self.video_path.stem}_audio.wav")
        
        try:
            # Use ffmpeg-python's stream processing
            (
                ffmpeg
                .input(str(self.video_path))
                .output(output_path, acodec='pcm_s16le', ac=1, ar='16k')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            return output_path
        except ffmpeg.Error as e:
            print(f"Error extracting audio: {e.stderr.decode() if e.stderr else str(e)}")
            raise
