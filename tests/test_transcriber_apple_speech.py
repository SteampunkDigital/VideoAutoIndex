import os
import subprocess
from pathlib import Path

from src.transcriber_apple_speech import AppleSpeechTranscriber


def test_apple_speech_init(dummy_wav):
    transcriber = AppleSpeechTranscriber(dummy_wav)

    assert transcriber.audio_path == dummy_wav
    assert transcriber.locale == "en-US"
    assert transcriber.compare_locale is None
    assert transcriber.source_path.name == "main.swift"
    assert transcriber.source_path.parent.name == "AppleSpeechTranscriber"
    assert transcriber.info_plist_path.name == "Info.plist"
    assert transcriber.info_plist_path.parent.name == "AppleSpeechTranscriber"
    assert transcriber.binary_path.name == "apple_speech_transcriber"


def test_apple_speech_japanese_locale(dummy_wav):
    transcriber = AppleSpeechTranscriber(dummy_wav, locale="ja-JP")

    assert transcriber.locale == "ja-JP"


def test_apple_speech_compare_locale(dummy_wav):
    transcriber = AppleSpeechTranscriber(dummy_wav, locale="ja-JP", compare_locale="en-US")

    assert transcriber.locale == "ja-JP"
    assert transcriber.compare_locale == "en-US"


def test_apple_speech_init_invalid_path():
    import pytest

    with pytest.raises(FileNotFoundError):
        AppleSpeechTranscriber("missing.wav")


def test_apple_speech_transcribe_runs_binary(dummy_wav, temp_dir, monkeypatch):
    transcriber = AppleSpeechTranscriber(dummy_wav, locale="en-GB")
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


def test_apple_speech_transcribe_runs_binary_with_compare_locale(dummy_wav, temp_dir, monkeypatch):
    transcriber = AppleSpeechTranscriber(dummy_wav, locale="ja-JP", compare_locale="en-US")
    monkeypatch.setattr(transcriber, "_ensure_binary", lambda: None)

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    transcript_path = os.path.join(temp_dir, "audio_transcript.json")
    subtitle_path = os.path.join(temp_dir, "audio_subtitles.srt")
    transcriber.transcribe(transcript_path, subtitle_path)

    assert calls[0][0][-2:] == ["--compare-locale", "en-US"]


def test_apple_speech_binary_current(dummy_wav, temp_dir):
    transcriber = AppleSpeechTranscriber(dummy_wav)
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


def test_apple_speech_parse_sdk_version(dummy_wav):
    transcriber = AppleSpeechTranscriber(dummy_wav)

    assert transcriber._parse_sdk_version(Path("MacOSX26.sdk")) == (26, 0)
    assert transcriber._parse_sdk_version(Path("MacOSX27.1.sdk")) == (27, 1)
    assert transcriber._parse_sdk_version(Path("MacOSX.sdk")) is None


def test_apple_speech_uses_newest_supported_sdk(dummy_wav, temp_dir, monkeypatch):
    transcriber = AppleSpeechTranscriber(dummy_wav)
    sdk_root = Path(temp_dir) / "SDKs"
    sdk_root.mkdir()
    (sdk_root / "MacOSX25.4.sdk").mkdir()
    (sdk_root / "MacOSX26.5.sdk").mkdir()
    (sdk_root / "MacOSX27.0.sdk").mkdir()
    monkeypatch.setattr("src.transcriber_apple_speech.MACOS_SDK_ROOTS", [sdk_root])

    sdk_path, sdk_version = transcriber._macos_sdk()

    assert sdk_path == str(sdk_root / "MacOSX27.0.sdk")
    assert sdk_version == (27, 0)


def test_apple_speech_sdk_roots_include_xcode_beta():
    import src.transcriber_apple_speech as apple_speech_module

    assert Path("/Applications/Xcode-beta.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs") in apple_speech_module.MACOS_SDK_ROOTS


def test_apple_speech_compile_target_matches_sdk(dummy_wav, temp_dir, monkeypatch):
    transcriber = AppleSpeechTranscriber(dummy_wav)
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


def test_apple_speech_missing_sdk(dummy_wav, monkeypatch):
    import pytest

    transcriber = AppleSpeechTranscriber(dummy_wav)
    monkeypatch.setattr("src.transcriber_apple_speech.MACOS_SDK_ROOTS", [])

    with pytest.raises(RuntimeError, match="macOS 26 SDK or newer"):
        transcriber._macos_sdk()
