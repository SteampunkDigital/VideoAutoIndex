import os
import json
import subprocess
import tempfile

class Transcriber:
    # Map model sizes to their corresponding model names
    MODEL_SIZES = {
        "tiny": "tiny",
        "base": "base",
        "small": "small",
        "medium": "medium",
        "large": "large-v3-turbo"  # Using latest turbo model for faster transcription
    }

    def __init__(self, audio_path: str, model_name: str = None, model_size: str = None):
        """
        Initialize the transcriber.
        
        Args:
            audio_path: Path to the input audio file
            model_name: Not used, kept for backward compatibility
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

        print(f"Using insanely-fast-whisper with {self.model_size} model...")
        
        try:
            # Create a temporary file for JSON output
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp_json:
                # Use insanely-fast-whisper to get transcription with timestamps
                cmd = [
                    "insanely-fast-whisper",
                    "--file-name", self.audio_path,
                    "--device-id", "mps",  # Use Metal Performance Shaders on macOS
                    "--model-name", f"openai/whisper-{self.model_size}",
                    "--transcript-path", tmp_json.name,
                    "--language", "en",  # Force English for consistency
                    "--batch-size", "4"  # Smaller batch size for better memory usage
                ]
                
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                
                # Read the JSON output
                with open(tmp_json.name, 'r') as f:
                    transcription = json.load(f)

            # Convert JSON to SRT format
            with open(subtitle_path, "w", encoding="utf-8") as f:
                for i, segment in enumerate(transcription['segments'], 1):
                    start_time = self._format_time(float(segment['start']))
                    end_time = self._format_time(float(segment['end']))
                    text = segment['text'].strip()

                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{text}\n\n")

            # Clean up temporary file
            os.unlink(tmp_json.name)
            
            return subtitle_path
            
        except subprocess.CalledProcessError as e:
            print(f"Error during transcription: {e.stderr}")
            raise
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
