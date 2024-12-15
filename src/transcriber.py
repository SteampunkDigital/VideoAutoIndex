# transcriber.py
import faster_whisper
import os

class Transcriber:
    def __init__(self, audio_path: str):
        """
        Initialize the transcriber.
        
        Args:
            audio_path: Path to the input audio file
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        self.audio_path = audio_path
        # Use tiny model for testing, allow downloads
        self.model = faster_whisper.WhisperModel("tiny", local_files_only=False)

    def transcribe(self, output_dir: str) -> str:
        """
        Transcribe the audio file using whisper and generate a subtitle track data.
        
        Args:
            output_dir: Directory to save the output files
            
        Returns:
            The path to the generated subtitle file.
        """
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Generate the subtitle file name
        audio_filename = os.path.basename(self.audio_path)
        subtitle_filename = f"{os.path.splitext(audio_filename)[0]}.srt"
        subtitle_path = os.path.join(output_dir, subtitle_filename)

        # Transcribe the audio
        result = self.model.transcribe(self.audio_path)
        segments = result[0]

        # Write the segments to the subtitle file
        with open(subtitle_path, "w") as f:
            for i, segment in enumerate(segments):
                start_time = self._format_time(segment.start)
                end_time = self._format_time(segment.end)
                transcript = segment.text

                f.write(f"{i+1}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{transcript}\n\n")

        return subtitle_path

    @staticmethod
    def _format_time(seconds: float) -> str:
        """
        Format time in seconds to the SRT format (HH:MM:SS,mmm).
        
        Args:
            seconds: Time in seconds.
        
        Returns:
            The formatted time string.
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        seconds = int(seconds)

        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
