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

    def add_chapters(self, analysis: List[Dict], output_dir: str) -> str:
        """
        Add chapters to the video based on topic timestamps.
        
        Args:
            analysis: List of topic dictionaries containing timestamps and descriptions
            output_dir: Directory to save the processed video
            
        Returns:
            Path to the processed video file with chapters
        """
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{self.video_path.stem}_chaptered{self.video_path.suffix}")
        
        # Create temporary metadata file
        metadata_path = os.path.join(output_dir, "ffmetadata.txt")
        with open(metadata_path, "w") as f:
            f.write(";FFMETADATA1\n")
            
            # Add chapters
            for i, topic in enumerate(analysis):
                # Convert timestamp to milliseconds
                start_time = self._parse_timestamp(topic['timestamp'])
                
                # For end time, use next topic's start time or video duration
                if i < len(analysis) - 1:
                    end_time = self._parse_timestamp(analysis[i + 1]['timestamp'])
                else:
                    # For the last chapter, get video duration using ffprobe
                    probe = ffmpeg.probe(str(self.video_path))
                    end_time = float(probe['format']['duration']) * 1000  # Convert to milliseconds
                
                # Write chapter metadata
                f.write("\n[CHAPTER]\n")
                f.write(f"TIMEBASE=1/1000\n")
                f.write(f"START={int(start_time)}\n")
                f.write(f"END={int(end_time)}\n")
                f.write(f"title={topic['topic']}\n")

        try:
            # Use ffmpeg-python for adding chapters
            (
                ffmpeg
                .input(str(self.video_path))
                .input(metadata_path)
                .output(output_path, map_metadata=1, codec='copy')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            # Clean up metadata file
            os.remove(metadata_path)
            
            return output_path
            
        except ffmpeg.Error as e:
            print(f"Error adding chapters: {e.stderr.decode() if e.stderr else str(e)}")
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
            raise

    def _parse_timestamp(self, timestamp: str) -> float:
        """
        Convert SRT timestamp format (HH:MM:SS,mmm) to milliseconds.
        
        Args:
            timestamp: Timestamp string in SRT format
        
        Returns:
            Time in milliseconds
        """
        # Split into time and milliseconds
        time_str, milliseconds = timestamp.split(',')
        hours, minutes, seconds = time_str.split(':')
        
        total_milliseconds = (
            int(hours) * 3600 * 1000 +
            int(minutes) * 60 * 1000 +
            int(seconds) * 1000 +
            int(milliseconds)
        )
        
        return total_milliseconds
