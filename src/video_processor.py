import ffmpeg
import os
from pathlib import Path

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
            stream = ffmpeg.input(str(self.video_path))
            stream = ffmpeg.output(stream, output_path, acodec='pcm_s16le', ac=1, ar='16k')
            ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            return output_path
        except ffmpeg.Error as e:
            print(f"Error extracting audio: {e.stderr.decode()}")
            raise

    def add_chapters(self, key_moments: list, output_dir: str) -> str:
        """
        Add chapters to the video based on key moments.
        
        Args:
            key_moments: List of tuples containing (timestamp, title) for each key moment
            output_dir: Directory to save the processed video
            
        Returns:
            Path to the processed video file with chapters
        """
        # TODO: Implement chapter addition using ffmpeg metadata
        # This will be implemented when we have the key_moments structure defined
        pass
