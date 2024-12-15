import os
from whisper_mps.whisper import transcribe

class Transcriber:
    # Map model sizes to their corresponding model names
    MODEL_SIZES = {
        "tiny": "tiny",
        "base": "base",
        "small": "small",
        "medium": "medium",
        "large": "large"
    }

    def __init__(self, audio_path: str, model_name: str = None, model_size: str = None):
        """
        Initialize the transcriber.
        
        Args:
            audio_path: Path to the input audio file
            model_name: Not used with whisper-mps, kept for backward compatibility
            model_size: Size of the Whisper model to use - tiny, base, small, medium, or large (default: None)
                       If not provided, defaults to "medium" for better stability
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        self.audio_path = audio_path
        
        # Determine which model to use
        if model_size:
            if model_size not in self.MODEL_SIZES:
                raise ValueError(f"Invalid model size. Must be one of: {', '.join(self.MODEL_SIZES.keys())}")
            self.model_size = self.MODEL_SIZES[model_size]
        else:
            self.model_size = "medium"  # Default to medium model for better stability

    def transcribe(self, output_dir: str) -> str:
        """
        Transcribe the audio file and generate a subtitle track data.
        
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

        print(f"Using whisper-mps with {self.model_size} model...")
        
        try:
            # Transcribe with whisper-mps
            result = transcribe(
                self.audio_path,
                model=self.model_size,
                language="en",  # Force English for consistency
            )

            # Write the segments to the subtitle file
            with open(subtitle_path, "w", encoding="utf-8") as f:
                for i, segment in enumerate(result["segments"], 1):
                    start_time = self._format_time(segment["start"])
                    end_time = self._format_time(segment["end"])
                    text = segment["text"].strip()

                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{text}\n\n")

            return subtitle_path
            
        except Exception as e:
            print(f"Error during transcription: {str(e)}")
            raise

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
