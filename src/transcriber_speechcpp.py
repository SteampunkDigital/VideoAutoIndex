"""Local speech.cpp recognition and diarization behind one transcription backend."""

import json
import os
import shutil
import subprocess
from pathlib import Path

from .transcript import normalize_chunk, write_transcript

DEFAULT_MODELS = {"en": "parakeet-tdt-0.6b-v3", "ja": "parakeet-tdt_ctc-0.6b-ja"}
STRONG_TRANSCRIPTION_MODEL = "nemotron-3.5-transcribe"
DIARIZATION_MODEL = "nemotron-3-diarization"
VAD_MODEL = "silero-vad"


def validate_model(model_name, language):
    if language not in DEFAULT_MODELS:
        raise ValueError("speech.cpp transcription supports en or ja")
    if model_name not in (DEFAULT_MODELS[language], STRONG_TRANSCRIPTION_MODEL):
        raise ValueError(
            f"speechcpp supports {DEFAULT_MODELS[language]} or {STRONG_TRANSCRIPTION_MODEL} "
            f"for {language} phrase timing"
        )


def speech_executable():
    override = os.environ.get("SPEECHCPP_BIN")
    if override:
        if not Path(override).is_file() or not os.access(override, os.X_OK):
            raise FileNotFoundError(f"SPEECHCPP_BIN is not executable: {override}")
        return override
    installed = shutil.which("speech")
    if installed:
        return installed
    local = Path(__file__).resolve().parents[1] / ".build" / "speechcpp" / "speech"
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    raise FileNotFoundError(
        "speech.cpp is required. Install its speech executable on PATH or set SPEECHCPP_BIN. "
        "See https://github.com/nyosegawa/speech.cpp/releases (tested with v0.10.1)."
    )


def _speaker_label(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("speech.cpp returned an invalid speaker number")
    return f"Speaker {value + 1}"


def speaker_timeline(regions):
    """Merge the same voice across VAD boundaries, preserving other voices' overlaps."""
    by_speaker = {}
    for region in regions:
        for span in region.get("speakers", []):
            chunk = normalize_chunk({"timestamp": [span.get("start"), span.get("end")],
                                     "text": "", "speaker": _speaker_label(span.get("speaker"))})
            by_speaker.setdefault(chunk["speaker"], []).append(chunk["timestamp"])
    timeline = []
    for speaker, spans in by_speaker.items():
        merged = []
        for start, end in sorted(spans):
            if merged and start <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        timeline.extend({"speaker": speaker, "timestamp": span} for span in merged)
    return sorted(timeline, key=lambda span: (span["timestamp"][0], span["speaker"]))


def attribute_phrase(start, end, timeline):
    """Use conservative temporal evidence; never duplicate mixed text across voices."""
    scores = {}
    for span in timeline:
        left, right = span["timestamp"]
        overlap = max(0.0, min(end, right) - max(start, left))
        if overlap:
            scores[span["speaker"]] = scores.get(span["speaker"], 0.0) + overlap
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return None
    speaker, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    length = end - start
    # A majority of the phrase must be supported, with a clear lead over other voices.
    return speaker if best >= 0.5 * length and best - second >= 0.25 * length else None


def normalize_result(payload, model_name, language):
    if not isinstance(payload, dict) or payload.get("stop") != "complete":
        raise ValueError("speech.cpp did not complete recognition")
    if payload.get("untimed"):
        raise ValueError(f"speech.cpp could not time its transcript: {payload['untimed']}")
    regions, segments = payload.get("regions"), payload.get("segments")
    if not isinstance(regions, list) or not isinstance(segments, list):
        raise ValueError("speech.cpp response requires timed segments and speaker regions")
    timeline = speaker_timeline(regions)
    chunks = []
    for index, segment in enumerate(segments):
        chunk = normalize_chunk({"id": f"phrase-{index}",
                                 "timestamp": [segment.get("start"), segment.get("end")],
                                 "text": segment.get("text")}, index)
        if not chunk["text"]:
            continue
        chunk["speaker"] = attribute_phrase(*chunk["timestamp"], timeline)
        chunks.append(chunk)
    if payload.get("text", "").strip() and not chunks:
        raise ValueError("speech.cpp returned text without timed phrases")
    chunks.sort(key=lambda chunk: chunk["timestamp"][0])
    return {
        "speakers": list(dict.fromkeys(span["speaker"] for span in timeline)),
        "chunks": chunks, "speaker_segments": timeline,
        "text": " ".join(chunk["text"] for chunk in chunks),
        "metadata": {"schema_version": 2, "backend": "speechcpp", "model": model_name,
                     "diarization_model": DIARIZATION_MODEL, "language": language,
                     "speaker_scope": "recording", "attribution": "phrase_time_overlap",
                     "overlap_text_recovery": "not_guaranteed"},
    }


class SpeechCppTranscriber:
    def __init__(self, audio_path, model_name=None, language="en"):
        self.audio_path = Path(audio_path)
        if not self.audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        self.language = language
        self.model_name = model_name or DEFAULT_MODELS.get(language)
        # These recognizers provide the timing required for phrase attribution.
        validate_model(self.model_name, language)

    def transcribe(self, transcript_path, subtitle_path):
        executable = speech_executable()
        print(f"Transcribing with speech.cpp: {self.model_name}; diarization: {DIARIZATION_MODEL}")
        command = [executable, "asr", self.model_name, "--timestamps", "--vad", VAD_MODEL,
                   "--diarize", DIARIZATION_MODEL, "--format", "json", str(self.audio_path)]
        # Keep stderr attached so loading, downloads, and progress remain visible.
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        payload = json.loads(result.stdout)
        data = normalize_result(payload, self.model_name, self.language)
        write_transcript(data, transcript_path, subtitle_path)
