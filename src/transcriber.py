import os
import torch
from transformers import pipeline
from transformers.utils import is_flash_attn_2_available

class Transcriber:
    def __init__(self, audio_path: str, model_name: str = "openai/whisper-large-v3"):
        """
        Initialize the transcriber.
        
        Args:
            audio_path: Path to the input audio file
            model_name: Name of the Whisper model to use (default: "openai/whisper-large-v3")
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        self.audio_path = audio_path
        
        # Auto-detect device
        if torch.backends.mps.is_available():
            device = "mps"  # Use Apple Silicon GPU
        elif torch.cuda.is_available():
            device = "cuda:0"
        else:
            device = "cpu"
            
        # Initialize the pipeline with optimizations
        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=model_name,
            torch_dtype=torch.float16,
            device=device,
            model_kwargs={"attn_implementation": "flash_attention_2"} if is_flash_attn_2_available() else {"attn_implementation": "sdpa"},
        )

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

        # Transcribe with optimized settings
        result = self.pipe(
            self.audio_path,
            chunk_length_s=30,
            batch_size=24,
            return_timestamps=True,
        )

        # Write the segments to the subtitle file
        with open(subtitle_path, "w", encoding="utf-8") as f:
            for i, chunk in enumerate(result["chunks"]):
                start_time = self._format_time(chunk["timestamp"][0])
                end_time = self._format_time(chunk["timestamp"][1])
                transcript = chunk["text"].strip()

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
