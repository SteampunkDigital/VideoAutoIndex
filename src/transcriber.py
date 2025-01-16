import os
import json
from datetime import timedelta
from faster_whisper import WhisperModel

class Transcriber:
    def __init__(self, audio_path: str, model_name: str = "base"):
        """
        Initialize the transcriber.
        
        Args:
            audio_path: Path to the audio file
            model_name: Name of the Whisper model to use
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        self.audio_path = audio_path
        self.model_name = model_name

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
        
        try:
            print(f"Using faster-whisper with model: {self.model_name}")
            # Initialize model with CPU compute type
            model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            
            # Transcribe audio
            print("Transcribing audio...")
            segments, _ = model.transcribe(self.audio_path, language="en")
            
            # Convert segments to JSON format
            chunks = []
            for segment in segments:
                chunks.append({
                    "timestamp": [segment.start, segment.end],
                    "text": segment.text
                })
            
            # Save JSON transcript
            with open(transcript_path, 'w', encoding='utf-8') as f:
                json.dump({"chunks": chunks}, f, indent=2)
            
            # Convert to SRT format
            print("Converting transcript to SRT format...")
            self._json_to_srt(transcript_path, subtitle_path)
            
        except Exception as e:
            print(f"Error during transcription: {str(e)}")
            raise
