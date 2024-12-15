import os
import subprocess

class Transcriber:
    def __init__(self, audio_path: str, model_name: str = None, model_size: str = None):
        """Initialize the transcriber."""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        self.audio_path = audio_path

    def transcribe(self, output_dir: str) -> str:
        """Transcribe audio to SRT subtitles."""
        os.makedirs(output_dir, exist_ok=True)
        
        subtitle_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(self.audio_path))[0]}.srt")
        
        print("Using insanely-fast-whisper...")
        
        try:
            subprocess.run([
                "insanely-fast-whisper",
                "--file-name", self.audio_path,
                "--transcript-path", subtitle_path,
                "--language", "en",
                "--device-id", "mps"
            ], check=True, capture_output=True, text=True)
            
            return subtitle_path
            
        except subprocess.CalledProcessError as e:
            print(f"Error during transcription: {e.stderr}")
            raise
