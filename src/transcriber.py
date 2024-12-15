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
        self.audio_path = audio_path
        self.model = faster_whisper.WhisperModel("large-v3", local_files_only=True)

    def transcribe(self, output_dir) -> list:
        """
        Transcribe the audio file using whisper and generate a subtitle track data.
        
        Returns:
            The path to the generated subtitle file.
        """
        result = self.model.transcribe(self.audio_path)
        segments = result["segments"]

        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Generate the subtitle file name
        audio_filename = os.path.basename(self.audio_path)
        subtitle_filename = f"{os.path.splitext(audio_filename)[0]}.srt"
        subtitle_path = os.path.join(output_dir, subtitle_filename)

        # Write the segments to the subtitle file
        with open(subtitle_path, "w") as f:
            for i, segment in enumerate(segments):
                start_time = self.format_time(segment["start"])
                end_time = self.format_time(segment["end"])
                transcript = segment["text"]

                f.write(f"{i+1}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{transcript}\n\n")

        return subtitle_path

    @staticmethod
    def format_time(seconds):
        """
        Format time in seconds to the SRT format (HH:MM:SS,mmm).
        
        Args:
            seconds: Time in seconds.
        
        Returns:
            The formatted time string.
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = round(seconds % 60, 3)
        milliseconds = int(seconds * 1000)

        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"
        
