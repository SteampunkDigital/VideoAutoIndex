# key_moments.py
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Literal
from anthropic import Anthropic
from openai import OpenAI
import openai
import anthropic

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
MINIMUM_MACOS_SDK = (26, 0)
MACOS_SDK_ROOTS = [
    Path("/Library/Developer/CommandLineTools/SDKs"),
    Path("/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs"),
]

class KeyMomentsExtractor:
    def __init__(
        self,
        subtitle_path: str,
        api_provider: Literal["anthropic", "openai", "apple"] = "anthropic",
        api_key: Optional[str] = None,
    ):
        """
        Initialize the key moments extractor.
        
        Args:
            subtitle_path: Path to the input subtitle file
            api_provider: Which provider to use ("anthropic", "openai", or "apple")
            api_key: API key for the specified cloud provider
        """
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
            
        self.subtitle_path = subtitle_path
        self.api_provider = api_provider
        self.project_root = Path(__file__).resolve().parents[1]
        self.source_path = self.project_root / "tools" / "apple_foundation_key_moments.swift"
        self.info_plist_path = self.project_root / "tools" / "apple_foundation_key_moments_Info.plist"
        self.binary_path = self.project_root / ".build" / "apple_foundation_key_moments"
        self.anthropic = None
        self.openai = None
        
        if api_provider == "anthropic":
            api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            self.anthropic = Anthropic(api_key=api_key)
        elif api_provider == "openai":
            api_key = api_key or os.environ.get("OPENAI_API_KEY")
            self.openai = OpenAI(api_key=api_key)
            self.openai_model = DEFAULT_OPENAI_MODEL
            print(f"Using OpenAI model: {self.openai_model}")
        elif api_provider == "apple":
            pass
        else:
            raise ValueError("api_provider must be 'anthropic', 'openai', or 'apple'")
    
    def extract_key_moments(self) -> List[Dict]:
        """
        Extract topics, key moments, and takeaways from the subtitle file using AI.
        
        Returns:
            List of topic dictionaries containing:
            - topic: Brief topic description
            - timestamp: Start time of the topic
            - key_moments: List of important moments within this topic
            - takeaways: List of actionable takeaways from this topic
        """
        # Read the subtitle file
        with open(self.subtitle_path, 'r') as f:
            subtitle_content = f.read()

        # Prepare the prompt for Claude
        prompt = f"""Analyze this meeting transcript and break it down into major topics.
        For each topic, identify its key moments and extract actionable takeaways.
        Format your response as a JSON array where each object represents a topic section with this structure:

        [
            {{
                "topic": "Brief topic description",
                "timestamp": "HH:MM:SS,mmm",
                "key_moments": [
                    {{
                        "description": "Description of an important moment",
                        "timestamp": "HH:MM:SS,mmm"
                    }}
                ],
                "takeaways": [
                    "Actionable takeaway or key decision 1",
                    "Actionable takeaway or key decision 2"
                ]
            }}
        ]

        Important:
        - Each topic should be a distinct discussion point or agenda item
        - Timestamps must match the exact SRT format from the transcript (HH:MM:SS,mmm)
        - Key moments should capture significant points, decisions, or transitions
        - Takeaways should be actionable items or important conclusions
        - Keep descriptions concise but informative

        Transcript:
        {subtitle_content}

        Respond only with the JSON array."""

        try:
            if self.api_provider == "anthropic":
                response_text = self._extract_with_anthropic(prompt)
                topics = self._parse_topics(response_text)
            elif self.api_provider == "openai":
                response_text = self._extract_with_openai(prompt)
                topics = self._parse_topics(response_text)
            else:
                topics = self._extract_with_apple()

            self._validate_topics(topics)
            return topics
            
        except Exception as e:
            # Re-raise with context if it's already a handled API error
            if "API" in str(e) or "rate limit" in str(e).lower() or "quota" in str(e).lower():
                raise
            # Otherwise, wrap as general processing error
            raise Exception(f"Failed to process meeting content: {str(e)}")

    def _extract_with_anthropic(self, prompt: str) -> str:
        try:
            if hasattr(self.anthropic.messages, "stream"):
                response_text = ""
                with self.anthropic.messages.stream(
                    model="claude-opus-4-1-20250805",
                    max_tokens=16384,
                    system="You are a meeting analyzer that breaks down discussions into topics, key moments, and takeaways. You only respond with properly formatted JSON.",
                    messages=[{
                        "role": "user",
                        "content": prompt
                    }]
                ) as stream:
                    for text in stream.text_stream:
                        response_text += text
                        print(".", end="", flush=True)
                print()
                return response_text

            response = self.anthropic.messages.create(
                model="claude-opus-4-1-20250805",
                max_tokens=16384,
                system="You are a meeting analyzer that breaks down discussions into topics, key moments, and takeaways. You only respond with properly formatted JSON.",
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            return response.content[0].text
        except anthropic.RateLimitError as e:
            raise Exception(f"Anthropic API rate limit exceeded. Please check your usage and billing: {str(e)}")
        except anthropic.AuthenticationError as e:
            raise Exception(f"Anthropic API authentication failed. Please check your API key: {str(e)}")
        except anthropic.APIConnectionError as e:
            raise Exception(f"Failed to connect to Anthropic API. Please check your internet connection: {str(e)}")
        except anthropic.InternalServerError as e:
            raise Exception(f"Anthropic API internal server error. Please try again later: {str(e)}")
        except anthropic.BadRequestError as e:
            raise Exception(f"Invalid request to Anthropic API: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected Anthropic API error: {str(e)}")

    def _extract_with_openai(self, prompt: str) -> str:
        try:
            api_params = {
                "model": self.openai_model,
                "messages": [
                    {"role": "system", "content": "You are a meeting analyzer that breaks down discussions into topics, key moments, and takeaways. You only respond with properly formatted JSON."},
                    {"role": "user", "content": prompt}
                ],
                "max_completion_tokens": 16384
            }

            response = self.openai.chat.completions.create(**api_params)
            return response.choices[0].message.content
        except openai.RateLimitError as e:
            raise Exception(f"OpenAI API rate limit exceeded or quota reached. Please check your usage and billing: {str(e)}")
        except openai.AuthenticationError as e:
            raise Exception(f"OpenAI API authentication failed. Please check your API key: {str(e)}")
        except openai.APIConnectionError as e:
            raise Exception(f"Failed to connect to OpenAI API. Please check your internet connection: {str(e)}")
        except openai.InternalServerError as e:
            raise Exception(f"OpenAI API internal server error. Please try again later: {str(e)}")
        except openai.BadRequestError as e:
            raise Exception(f"Invalid request to OpenAI API: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected OpenAI API error: {str(e)}")

    def _extract_with_apple(self) -> List[Dict]:
        self._ensure_binary()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "meeting_analysis.json")
            command = [
                str(self.binary_path),
                "--srt",
                self.subtitle_path,
                "--output",
                output_path,
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
                message = f"Apple FoundationModels key moments failed with exit code {error.returncode}."
                if details:
                    message = f"{message}\n{details}"
                raise RuntimeError(message) from error

            with open(output_path, "r") as f:
                return json.load(f)

    def _parse_topics(self, response_text: str) -> List[Dict]:
        try:
            return json.loads(response_text)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Raw response content: {response_text}")
            raise Exception(f"Failed to parse API response as JSON: {str(e)}")

    def _validate_topics(self, topics: List[Dict]) -> None:
        if not isinstance(topics, list):
            raise ValueError("Expected a list of topics")

        for topic in topics:
            if not isinstance(topic, dict):
                raise ValueError("Invalid topic format")

            required_fields = ['topic', 'timestamp', 'key_moments', 'takeaways']
            if not all(field in topic for field in required_fields):
                raise ValueError(f"Missing required fields in topic: {required_fields}")

            self._validate_timestamp_format(topic['timestamp'])

            if not isinstance(topic['key_moments'], list):
                raise ValueError("Expected list of key moments")
            for moment in topic['key_moments']:
                if not isinstance(moment, dict):
                    raise ValueError("Invalid key moment format")
                if 'description' not in moment or 'timestamp' not in moment:
                    raise ValueError("Missing required fields in key moment")
                self._validate_timestamp_format(moment['timestamp'])

            if not isinstance(topic['takeaways'], list):
                raise ValueError("Expected list of takeaways")
            for takeaway in topic['takeaways']:
                if not isinstance(takeaway, str):
                    raise ValueError("Invalid takeaway format")

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

        sdk_path = subprocess.run(
            ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        sdk_version_output = subprocess.run(
            ["xcrun", "--sdk", "macosx", "--show-sdk-version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        sdk_version = self._parse_version(sdk_version_output)
        if sdk_version >= MINIMUM_MACOS_SDK:
            return sdk_path, sdk_version

        raise RuntimeError(
            "Apple FoundationModels key moments require the macOS 26 SDK or newer. "
            "Install Xcode/CommandLineTools with MacOSX26.x.sdk or newer."
        )

    def _parse_sdk_version(self, sdk_path: Path) -> tuple[int, int] | None:
        match = re.fullmatch(r"MacOSX(\d+)(?:\.(\d+))?\.sdk", sdk_path.name)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2) or 0)

    def _parse_version(self, version: str) -> tuple[int, int]:
        match = re.match(r"^(\d+)(?:\.(\d+))?", version)
        if not match:
            raise RuntimeError(f"Unable to parse macOS SDK version: {version}")
        return int(match.group(1)), int(match.group(2) or 0)

    def _validate_timestamp_format(self, timestamp: str) -> None:
        """
        Validate that a timestamp string matches the SRT format (HH:MM:SS,mmm).
        
        Args:
            timestamp: Timestamp string to validate
            
        Raises:
            ValueError: If timestamp format is invalid
        """
        try:
            # Split into time and milliseconds
            time_parts = timestamp.split(',')
            if len(time_parts) != 2:
                raise ValueError
                
            # Validate milliseconds
            if not time_parts[1].isdigit() or len(time_parts[1]) != 3:
                raise ValueError
                
            # Split time into hours, minutes, seconds
            hours, minutes, seconds = time_parts[0].split(':')
            
            # Validate each component
            if not (hours.isdigit() and minutes.isdigit() and seconds.isdigit()):
                raise ValueError
            if not (len(hours) == 2 and len(minutes) == 2 and len(seconds) == 2):
                raise ValueError
            if not (0 <= int(hours) <= 99 and 0 <= int(minutes) <= 59 and 0 <= int(seconds) <= 59):
                raise ValueError
                
        except (ValueError, IndexError):
            raise ValueError(
                f"Invalid timestamp format: {timestamp}. Expected format: HH:MM:SS,mmm"
            )

    def _parse_timestamp(self, timestamp: str) -> float:
        """
        Convert SRT timestamp format (HH:MM:SS,mmm) to seconds.
        
        Args:
            timestamp: Timestamp string in SRT format
        
        Returns:
            Time in seconds as a float
        """
        # Split into time and milliseconds
        time_str, milliseconds = timestamp.split(',')
        hours, minutes, seconds = time_str.split(':')
        
        total_seconds = (
            int(hours) * 3600 +
            int(minutes) * 60 +
            int(seconds) +
            int(milliseconds) / 1000
        )
        
        return total_seconds
