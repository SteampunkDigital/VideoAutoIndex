import os
import subprocess
from pathlib import Path

import pytest

from src.transcriber_apple_dictation import AppleDictationTranscriber


def test_apple_dictation_init(dummy_wav):
    transcriber = AppleDictationTranscriber(dummy_wav)

    assert transcriber.audio_path == dummy_wav
    assert transcriber.locale == "en-US"


def test_apple_dictation_init_invalid_path():
    with pytest.raises(FileNotFoundError):
        AppleDictationTranscriber("missing.wav")


def test_apple_dictation_transcribe_runs_binary(dummy_wav, temp_dir, monkeypatch):
    transcriber = AppleDictationTranscriber(dummy_wav, locale="en-GB")
    monkeypatch.setattr(transcriber, "_ensure_binary", lambda: None)

    calls = []

    def fake_run(command, check):
        calls.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    transcript_path = os.path.join(temp_dir, "nested", "audio_transcript.json")
    subtitle_path = os.path.join(temp_dir, "nested", "audio_subtitles.srt")
    transcriber.transcribe(transcript_path, subtitle_path)

    assert os.path.isdir(os.path.dirname(transcript_path))
    assert calls == [
        (
            [
                str(transcriber.binary_path),
                "--audio",
                dummy_wav,
                "--transcript",
                transcript_path,
                "--srt",
                subtitle_path,
                "--locale",
                "en-GB",
            ],
            True,
        )
    ]


def test_apple_dictation_binary_current(dummy_wav, temp_dir):
    transcriber = AppleDictationTranscriber(dummy_wav)
    transcriber.source_path = Path(temp_dir) / "tool.swift"
    transcriber.binary_path = Path(temp_dir) / "tool"

    with open(transcriber.source_path, "w") as f:
        f.write("source")

    assert transcriber._binary_is_current() is False

    with open(transcriber.binary_path, "w") as f:
        f.write("binary")

    os.utime(transcriber.binary_path, None)
    assert transcriber._binary_is_current() is True


def test_apple_dictation_missing_sdk(dummy_wav, monkeypatch):
    transcriber = AppleDictationTranscriber(dummy_wav)
    monkeypatch.setattr("src.transcriber_apple_dictation.Path.exists", lambda self: False)

    with pytest.raises(RuntimeError, match="macOS 26 SDK"):
        transcriber._macos_26_sdk_path()
