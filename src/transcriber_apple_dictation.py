import os
import subprocess
from pathlib import Path


class AppleDictationTranscriber:
    def __init__(self, audio_path: str, locale: str = "en-US"):
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        self.audio_path = audio_path
        self.locale = locale
        self.project_root = Path(__file__).resolve().parents[1]
        self.source_path = self.project_root / "tools" / "apple_dictation_transcriber.swift"
        self.binary_path = self.project_root / ".build" / "apple_dictation_transcriber"

    def transcribe(self, transcript_path: str, subtitle_path: str):
        self._ensure_binary()
        self._ensure_parent_dir(transcript_path)
        self._ensure_parent_dir(subtitle_path)

        subprocess.run(
            [
                str(self.binary_path),
                "--audio",
                self.audio_path,
                "--transcript",
                transcript_path,
                "--srt",
                subtitle_path,
                "--locale",
                self.locale,
            ],
            check=True,
        )

    def _ensure_binary(self):
        if self._binary_is_current():
            return
        os.makedirs(self.binary_path.parent, exist_ok=True)
        sdk_path = self._macos_26_sdk_path()
        subprocess.run(
            [
                "xcrun",
                "swiftc",
                "-sdk",
                sdk_path,
                "-target",
                "arm64-apple-macos26.0",
                "-parse-as-library",
                str(self.source_path),
                "-o",
                str(self.binary_path),
            ],
            check=True,
        )

    def _binary_is_current(self) -> bool:
        if not self.binary_path.exists():
            return False
        return self.binary_path.stat().st_mtime >= self.source_path.stat().st_mtime

    def _macos_26_sdk_path(self) -> str:
        candidates = [
            Path("/Library/Developer/CommandLineTools/SDKs/MacOSX26.2.sdk"),
            Path("/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.2.sdk"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        raise RuntimeError(
            "Apple DictationTranscriber requires the macOS 26 SDK. "
            "Install Xcode/CommandLineTools with MacOSX26.x.sdk."
        )

    def _ensure_parent_dir(self, path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
