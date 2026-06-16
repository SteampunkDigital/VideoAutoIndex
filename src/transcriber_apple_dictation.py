import os
import re
import subprocess
from pathlib import Path


MINIMUM_MACOS_SDK = (26, 0)
MACOS_SDK_ROOTS = [
    Path("/Library/Developer/CommandLineTools/SDKs"),
    Path("/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs"),
]


class AppleDictationTranscriber:
    def __init__(self, audio_path: str, locale: str = "en-US"):
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        self.audio_path = audio_path
        self.locale = locale
        self.project_root = Path(__file__).resolve().parents[1]
        self.source_path = self.project_root / "tools" / "apple_speechrecognizer_transcriber.swift"
        self.info_plist_path = self.project_root / "tools" / "apple_speechrecognizer_transcriber_Info.plist"
        self.binary_path = self.project_root / ".build" / "apple_speechrecognizer_transcriber"

    def transcribe(self, transcript_path: str, subtitle_path: str):
        self._ensure_binary()
        self._ensure_parent_dir(transcript_path)
        self._ensure_parent_dir(subtitle_path)

        command = [
            str(self.binary_path),
            "--audio",
            self.audio_path,
            "--transcript",
            transcript_path,
            "--srt",
            subtitle_path,
            "--locale",
            self.locale,
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            details = "\n".join(
                part.strip()
                for part in (error.stdout, error.stderr)
                if part and part.strip()
            )
            message = f"Apple SpeechRecognizer transcriber failed with exit code {error.returncode}."
            if details:
                message = f"{message}\n{details}"
            raise RuntimeError(message) from error

    def _ensure_binary(self):
        if self._binary_is_current():
            return
        os.makedirs(self.binary_path.parent, exist_ok=True)
        sdk_path, sdk_version = self._macos_sdk()
        subprocess.run(
            [
                "xcrun",
                "swiftc",
                "-sdk",
                sdk_path,
                "-target",
                f"arm64-apple-macos{sdk_version[0]}.{sdk_version[1]}",
                "-parse-as-library",
                str(self.source_path),
                "-Xlinker",
                "-sectcreate",
                "-Xlinker",
                "__TEXT",
                "-Xlinker",
                "__info_plist",
                "-Xlinker",
                str(self.info_plist_path),
                "-o",
                str(self.binary_path),
            ],
            check=True,
        )

    def _binary_is_current(self) -> bool:
        if not self.binary_path.exists():
            return False
        binary_mtime = self.binary_path.stat().st_mtime
        return (
            binary_mtime >= self.source_path.stat().st_mtime
            and binary_mtime >= self.info_plist_path.stat().st_mtime
        )

    def _macos_sdk(self) -> tuple[str, tuple[int, int]]:
        candidates = []
        for sdk_root in MACOS_SDK_ROOTS:
            for candidate in sdk_root.glob("MacOSX*.sdk"):
                version = self._parse_sdk_version(candidate)
                if version is not None and version >= MINIMUM_MACOS_SDK:
                    candidates.append((version, candidate))

        if candidates:
            version, candidate = max(candidates, key=lambda item: item[0])
            return str(candidate), version

        raise RuntimeError(
            "Apple DictationTranscriber requires the macOS 26 SDK or newer. "
            "Install Xcode/CommandLineTools with MacOSX26.x.sdk or newer."
        )

    def _parse_sdk_version(self, sdk_path: Path) -> tuple[int, int] | None:
        match = re.fullmatch(r"MacOSX(\d+)(?:\.(\d+))?\.sdk", sdk_path.name)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2) or 0)

    def _ensure_parent_dir(self, path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
