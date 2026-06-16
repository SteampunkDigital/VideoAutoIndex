import os
import subprocess
from pathlib import Path

import pytest

from src.transcriber_apple_dictation import AppleDictationTranscriber


def test_apple_dictation_init(dummy_wav):
    transcriber = AppleDictationTranscriber(dummy_wav)

    assert transcriber.audio_path == dummy_wav
    assert transcriber.locale == "en-US"
    assert transcriber.source_path.name == "apple_dictation_transcriber.swift"
    assert transcriber.info_plist_path.name == "apple_dictation_transcriber_Info.plist"
    assert transcriber.binary_path.name == "apple_dictation_transcriber"


def test_apple_dictation_init_invalid_path():
    with pytest.raises(FileNotFoundError):
        AppleDictationTranscriber("missing.wav")


def test_apple_dictation_transcribe_runs_binary(dummy_wav, temp_dir, monkeypatch):
    transcriber = AppleDictationTranscriber(dummy_wav, locale="en-GB")
    monkeypatch.setattr(transcriber, "_ensure_binary", lambda: None)

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
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
            {"check": True, "capture_output": True, "text": True},
        )
    ]


def test_apple_dictation_binary_current(dummy_wav, temp_dir):
    transcriber = AppleDictationTranscriber(dummy_wav)
    transcriber.source_path = Path(temp_dir) / "tool.swift"
    transcriber.info_plist_path = Path(temp_dir) / "tool.plist"
    transcriber.binary_path = Path(temp_dir) / "tool"

    with open(transcriber.source_path, "w") as f:
        f.write("source")
    with open(transcriber.info_plist_path, "w") as f:
        f.write("plist")

    assert transcriber._binary_is_current() is False

    with open(transcriber.binary_path, "w") as f:
        f.write("binary")

    os.utime(transcriber.binary_path, None)
    assert transcriber._binary_is_current() is True


def test_apple_dictation_parse_sdk_version(dummy_wav):
    transcriber = AppleDictationTranscriber(dummy_wav)

    assert transcriber._parse_sdk_version(Path("MacOSX26.sdk")) == (26, 0)
    assert transcriber._parse_sdk_version(Path("MacOSX27.1.sdk")) == (27, 1)
    assert transcriber._parse_sdk_version(Path("MacOSX.sdk")) is None


def test_apple_dictation_uses_newest_supported_sdk(dummy_wav, temp_dir, monkeypatch):
    transcriber = AppleDictationTranscriber(dummy_wav)
    sdk_root = Path(temp_dir) / "SDKs"
    sdk_root.mkdir()
    (sdk_root / "MacOSX25.4.sdk").mkdir()
    (sdk_root / "MacOSX26.5.sdk").mkdir()
    (sdk_root / "MacOSX27.0.sdk").mkdir()
    monkeypatch.setattr("src.transcriber_apple_dictation.MACOS_SDK_ROOTS", [sdk_root])

    sdk_path, sdk_version = transcriber._macos_sdk()

    assert sdk_path == str(sdk_root / "MacOSX27.0.sdk")
    assert sdk_version == (27, 0)


def test_apple_dictation_compile_target_matches_sdk(dummy_wav, temp_dir, monkeypatch):
    transcriber = AppleDictationTranscriber(dummy_wav)
    transcriber.source_path = Path(temp_dir) / "tool.swift"
    transcriber.info_plist_path = Path(temp_dir) / "tool.plist"
    transcriber.binary_path = Path(temp_dir) / "tool"
    transcriber.source_path.write_text("source")
    transcriber.info_plist_path.write_text("plist")
    monkeypatch.setattr(transcriber, "_macos_sdk", lambda: ("/tmp/MacOSX27.0.sdk", (27, 0)))

    calls = []

    def fake_run(command, check):
        calls.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    transcriber._ensure_binary()

    assert calls == [
        (
            [
                "xcrun",
                "swiftc",
                "-sdk",
                "/tmp/MacOSX27.0.sdk",
                "-target",
                "arm64-apple-macos27.0",
                "-parse-as-library",
                str(transcriber.source_path),
                "-Xlinker",
                "-sectcreate",
                "-Xlinker",
                "__TEXT",
                "-Xlinker",
                "__info_plist",
                "-Xlinker",
                str(transcriber.info_plist_path),
                "-o",
                str(transcriber.binary_path),
            ],
            True,
        )
    ]


def test_apple_dictation_missing_sdk(dummy_wav, monkeypatch):
    transcriber = AppleDictationTranscriber(dummy_wav)
    monkeypatch.setattr("src.transcriber_apple_dictation.MACOS_SDK_ROOTS", [])

    with pytest.raises(RuntimeError, match="macOS 26 SDK or newer"):
        transcriber._macos_sdk()
