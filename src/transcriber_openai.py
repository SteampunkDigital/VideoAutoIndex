"""File transcription with speaker labels and potentially overlapping segments."""

import math
import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI

from .transcript import normalize_chunk, write_transcript

DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
MAX_UPLOAD_BYTES = 24_000_000  # Leave headroom below the API's 25 MB limit.
SPLIT_SECONDS = 20 * 60


def validate_model(model):
    if model != DEFAULT_TRANSCRIPTION_MODEL:
        raise ValueError(
            f"OpenAI transcription requires {DEFAULT_TRANSCRIPTION_MODEL} for speaker labels "
            "and timestamps. gpt-transcribe needs a separate diarization/alignment stage."
        )


class OpenAITranscriber:
    def __init__(self, audio_path, api_key=None, model_name=DEFAULT_TRANSCRIPTION_MODEL, language="en"):
        self.audio_path = Path(audio_path)
        if not self.audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        validate_model(model_name)
        self.model_name = model_name
        self.language = language
        # The SDK retries transient connection, rate-limit and server errors twice.
        self.client = OpenAI(api_key=api_key, max_retries=2, timeout=600.0)

    def _duration(self):
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", str(self.audio_path)],
            check=True, capture_output=True, text=True,
        )
        duration = float(result.stdout.strip())
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Audio must have a finite, positive duration")
        return duration

    def _encode(self, output, start=0, duration=None):
        command = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", str(start),
                   "-i", str(self.audio_path)]
        if duration is not None:
            command.extend(["-t", str(duration)])
        command.extend(["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame",
                        "-b:a", "32k", str(output)])
        subprocess.run(command, check=True, capture_output=True, text=True)

    def _prepare_uploads(self, directory):
        duration = self._duration()
        if self.audio_path.stat().st_size <= MAX_UPLOAD_BYTES:
            return [(self.audio_path, 0.0, duration)]
        compressed = directory / "audio.mp3"
        self._encode(compressed)
        if compressed.stat().st_size <= MAX_UPLOAD_BYTES:
            return [(compressed, 0.0, duration)]
        # Non-overlapping transport windows avoid duplicating boundary audio.
        # Speakers are scoped per request; continuity across requests is unknown.
        uploads = []
        for index, start in enumerate(range(0, math.ceil(duration), SPLIT_SECONDS)):
            length = min(SPLIT_SECONDS, duration - start)
            path = directory / f"part-{index + 1}.mp3"
            self._encode(path, start, length)
            if path.stat().st_size > MAX_UPLOAD_BYTES:
                raise ValueError("Encoded audio part exceeds the upload limit")
            uploads.append((path, float(start), length))
        return uploads

    def transcribe(self, transcript_path, subtitle_path):
        print(f"Transcribing with OpenAI: {self.model_name} ({self.language})")
        chunks = []
        with tempfile.TemporaryDirectory(prefix="openai-transcribe-") as directory:
            uploads = self._prepare_uploads(Path(directory))
            multipart = len(uploads) > 1
            if multipart:
                print("Audio requires multiple uploads; speaker labels are local to each part.")
            for part, (path, offset, duration) in enumerate(uploads, 1):
                with path.open("rb") as audio:
                    response = self.client.audio.transcriptions.create(
                        file=audio, model=self.model_name, response_format="diarized_json",
                        chunking_strategy="auto", language=self.language,
                    )
                payload = response.model_dump()
                segments = payload.get("segments")
                if not isinstance(segments, list):
                    raise ValueError("OpenAI response did not include timestamped speaker segments")
                if not segments and payload.get("text", "").strip():
                    raise ValueError("OpenAI returned text without timestamped speaker segments")
                for index, segment in enumerate(segments):
                    chunk = normalize_chunk({
                        "id": f"part-{part}-segment-{index}",
                        "timestamp": [segment.get("start"), segment.get("end")],
                        "text": segment.get("text"), "speaker": segment.get("speaker"),
                    }, index)
                    start, end = chunk["timestamp"]
                    # Small codec padding/rounding errors can extend past the window.
                    if end > duration + 0.25:
                        raise ValueError("OpenAI segment extends beyond its audio window")
                    end = min(end, duration)
                    if start >= end:
                        raise ValueError("OpenAI segment lies outside its audio window")
                    chunk["timestamp"] = [start + offset, end + offset]
                    if multipart and chunk["speaker"] is not None:
                        chunk["speaker"] = f"Part {part} / {chunk['speaker']}"
                    if chunk["text"]:
                        chunks.append(chunk)
        chunks.sort(key=lambda chunk: chunk["timestamp"][0])
        data = {
            "speakers": list(dict.fromkeys(c["speaker"] for c in chunks if c["speaker"])),
            "chunks": chunks, "text": " ".join(c["text"] for c in chunks),
            "metadata": {"schema_version": 2, "backend": "openai", "model": self.model_name,
                         "language": self.language, "speaker_scope": "upload" if multipart else "recording",
                         "upload_count": len(uploads)},
        }
        write_transcript(data, transcript_path, subtitle_path)
