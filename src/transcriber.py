import os
import json
import subprocess
import platform
from datetime import timedelta

class Transcriber:
    def __init__(self, audio_path: str, model_name: str = "openai/whisper-large-v3-turbo", device_id: str = None):
        """
        Initialize the transcriber.
        
        Args:
            audio_path: Path to the audio file
            model_name: Name of the Whisper model to use
            device_id: Device ID for inference ("0" for CPU/CUDA, "mps" for Apple Silicon, defaults to "0")
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        self.audio_path = audio_path
        self.model_name = model_name
        # Default to "mps" on macOS/Apple Silicon, "0" otherwise
        self.device_id = device_id or ("mps" if platform.system() == "Darwin" and platform.machine() == "arm64" else "0")

    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        td = timedelta(seconds=seconds)
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        seconds = td.seconds % 60
        milliseconds = round(td.microseconds / 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _json_to_srt(self, json_path: str, srt_path: str):
        """Convert JSON transcript to SRT format."""
        with open(json_path, 'r') as f:
            data = json.load(f)

        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, chunk in enumerate(data['chunks'], 1):
                # Write sequence number
                f.write(f"{i}\n")
                
                # Write timestamps
                start_time = self._format_timestamp(chunk['timestamp'][0])
                end_time = self._format_timestamp(chunk['timestamp'][1])
                f.write(f"{start_time} --> {end_time}\n")
                
                # Write text
                f.write(f"{chunk['text'].strip()}\n\n")

    def transcribe(self, transcript_path: str, subtitle_path: str):
        """
        Transcribe audio to JSON transcript and SRT subtitles.
        
        Args:
            transcript_path: Path to save the JSON transcript
            subtitle_path: Path to save the SRT subtitles
        """
        os.makedirs(os.path.dirname(transcript_path), exist_ok=True)
        os.makedirs(os.path.dirname(subtitle_path), exist_ok=True)
        
        print("Using insanely-fast-whisper...")
        print(f"Model: {self.model_name}")
        print(f"Device: {self.device_id}")
        
        try:
            # Run transcription to get JSON output
            result = subprocess.run([
                "insanely-fast-whisper",
                "--file-name", self.audio_path,
                "--transcript-path", transcript_path,
                "--language", "en",
                "--device-id", self.device_id,
                "--model", self.model_name,
                "--task", "transcribe"
            ], check=True, capture_output=True, text=True)
            
            print(result.stdout)
            
            # Convert JSON to SRT format
            print("Converting transcript to SRT format...")
            self._json_to_srt(transcript_path, subtitle_path)
            
        except subprocess.CalledProcessError as e:
            print(f"Error during transcription: {e.stderr}")
            raise
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse JSON transcript at {transcript_path}")
            print(f"JSON Error: {str(e)}")
            raise
        except Exception as e:
            print(f"Unexpected error during transcription: {str(e)}")
            raise
