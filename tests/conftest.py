import pytest
import os
import sys
import json
import tempfile
from pathlib import Path

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

@pytest.fixture(autouse=True)
def mock_anthropic_key(monkeypatch):
    """Mock Anthropic API key for testing. This fixture runs automatically for all tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

@pytest.fixture
def temp_dir():
    """Provide a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname

@pytest.fixture
def sample_video(temp_dir):
    """Create a small test video file using ffmpeg."""
    video_path = os.path.join(temp_dir, "test_video.mp4")
    
    # Create a 1-second test video with a black screen and silence
    os.system(
        f'ffmpeg -f lavfi -i color=c=black:s=320x240:d=1 '
        f'-f lavfi -i anullsrc=r=44100:cl=mono:d=1 '
        f'-c:v libx264 -c:a aac -t 1 {video_path} '
        f'-y >/dev/null 2>&1'
    )
    
    if not os.path.exists(video_path):
        pytest.skip("Failed to create test video. Is ffmpeg installed?")
    
    yield video_path
    
    # Cleanup is handled by temp_dir fixture

@pytest.fixture
def mock_anthropic(monkeypatch):
    """Mock Anthropic API for testing."""
    class Content:
        def __init__(self, text):
            self.text = text

    class MockMessage:
        def __init__(self):
            sample_response = [{
                "topic": "Quarterly Planning Overview",
                "timestamp": "00:00:00,000",
                "key_moments": [
                    {
                        "description": "Meeting introduction and agenda setting",
                        "timestamp": "00:00:00,000"
                    },
                    {
                        "description": "Q3 performance review",
                        "timestamp": "00:00:10,000"
                    }
                ],
                "takeaways": [
                    "Q3 targets exceeded by 15%",
                    "Q4 goals and strategy to be discussed"
                ]
            }]
            self.content = [Content(json.dumps(sample_response))]

    class MockAnthropicMessages:
        def create(self, model=None, max_tokens=None, temperature=None, system=None, messages=None, **kwargs):
            return MockMessage()

    class MockAnthropic:
        def __init__(self, api_key=None):
            self.messages = MockAnthropicMessages()
            self.api_key = api_key

        def __call__(self, api_key=None):
            return self

    # Create an instance of MockAnthropic
    mock_anthropic = MockAnthropic()
    
    # Mock both the class and the instance
    monkeypatch.setattr("anthropic.Anthropic", mock_anthropic)
    monkeypatch.setattr("src.key_moments.Anthropic", mock_anthropic)

@pytest.fixture
def dummy_srt(temp_dir):
    """Create a dummy SRT file for testing."""
    srt_content = """1
00:00:00,000 --> 00:00:05,000
Test subtitle content.

2
00:00:05,000 --> 00:00:10,000
More test content.
"""
    srt_path = os.path.join(temp_dir, "test.srt")
    with open(srt_path, "w") as f:
        f.write(srt_content)
    return srt_path

@pytest.fixture
def dummy_wav(temp_dir):
    """Create a dummy WAV file for testing."""
    wav_path = os.path.join(temp_dir, "test.wav")
    # Create a 1-second silent WAV file
    os.system(
        f'ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono:d=1 '
        f'-acodec pcm_s16le {wav_path} '
        f'-y >/dev/null 2>&1'
    )
    if not os.path.exists(wav_path):
        pytest.skip("Failed to create test audio. Is ffmpeg installed?")
    return wav_path

@pytest.fixture
def test_data_dir():
    """Get the test_data directory path."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_data")
