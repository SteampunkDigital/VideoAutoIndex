import pytest
import os
import json
import subprocess
from pathlib import Path
from src.main import process_video, check_ffmpeg, check_python_dependencies, check_api_key

@pytest.fixture
def mock_anthropic_key(monkeypatch):
    """Mock Anthropic API key for testing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response."""
    return {
        "content": json.dumps([
            {
                "topic": "Project Status Update",
                "timestamp": "00:00:00,000",
                "key_moments": [
                    {
                        "description": "Meeting introduction",
                        "timestamp": "00:00:00,000"
                    }
                ],
                "takeaways": [
                    "Project kickoff successful"
                ]
            }
        ])
    }

@pytest.fixture
def mock_anthropic(monkeypatch, mock_anthropic_response):
    """Mock Anthropic API for testing."""
    class MockMessage:
        def __init__(self, content):
            self.content = mock_anthropic_response["content"]
    
    class MockAnthropicMessages:
        def create(self, **kwargs):
            return MockMessage(None)
    
    class MockAnthropic:
        def __init__(self, api_key):
            self.messages = MockAnthropicMessages()
    
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("src.key_moments.Anthropic", MockAnthropic)

def test_check_ffmpeg_installed(monkeypatch):
    """Test ffmpeg check when ffmpeg is installed."""
    def mock_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0)
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert check_ffmpeg() is True

def test_check_ffmpeg_not_installed(monkeypatch):
    """Test ffmpeg check when ffmpeg is not installed."""
    def mock_run(*args, **kwargs):
        raise FileNotFoundError()
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert check_ffmpeg() is False

def test_check_python_dependencies_all_installed(monkeypatch):
    """Test Python dependencies check when all required packages are installed."""
    def mock_import(*args, **kwargs):
        return True
    
    monkeypatch.setattr("builtins.__import__", mock_import)
    assert check_python_dependencies() is True

def test_check_python_dependencies_missing(monkeypatch):
    """Test Python dependencies check when a package is missing."""
    def mock_import(name, *args, **kwargs):
        if name == "insanely_fast_whisper":
            raise ImportError(f"No module named '{name}'")
        return True
    
    monkeypatch.setattr("builtins.__import__", mock_import)
    assert check_python_dependencies() is False

def test_check_api_key_set(monkeypatch):
    """Test API key check when key is set."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy_key")
    assert check_api_key() is True

def test_check_api_key_not_set(monkeypatch):
    """Test API key check when key is not set."""
    if "ANTHROPIC_API_KEY" in os.environ:
        monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert check_api_key() is False

@pytest.mark.integration
def test_full_pipeline(sample_video, temp_dir, mock_anthropic, monkeypatch):
    """Test the complete video processing pipeline."""
    # Mock Transcriber to use tiny model
    from src.transcriber import Transcriber
    original_init = Transcriber.__init__
    def mock_init(self, audio_path, model_size="tiny"):
        return original_init(self, audio_path, model_size=model_size)
    monkeypatch.setattr(Transcriber, "__init__", mock_init)
    
    process_video(sample_video, temp_dir)
    
    # Check that all expected output files were created
    expected_files = [
        "*_audio.wav",      # Extracted audio
        "*.srt",            # Subtitles
        "meeting_analysis.json",  # Analysis
        "*_chaptered.mp4",  # Chaptered video
        "meeting_summary.html"    # Web summary
    ]
    
    for pattern in expected_files:
        matches = list(Path(temp_dir).glob(pattern))
        assert len(matches) > 0, f"Missing output file matching {pattern}"
    
    # Validate analysis JSON
    with open(os.path.join(temp_dir, "meeting_analysis.json")) as f:
        analysis = json.load(f)
        assert isinstance(analysis, list)
        assert len(analysis) > 0
        
        topic = analysis[0]
        assert all(key in topic for key in ["topic", "timestamp", "key_moments", "takeaways"])
    
    # Validate HTML summary
    with open(os.path.join(temp_dir, "meeting_summary.html")) as f:
        content = f.read()
        assert "Meeting Summary" in content
        assert "video" in content.lower()
        assert "timestamp" in content.lower()
        assert "key-moment" in content.lower()
        assert "takeaway" in content.lower()

@pytest.mark.integration
def test_pipeline_creates_output_dir(sample_video, temp_dir, mock_anthropic, monkeypatch):
    """Test that the pipeline creates nested output directories."""
    # Mock Transcriber to use tiny model
    from src.transcriber import Transcriber
    original_init = Transcriber.__init__
    def mock_init(self, audio_path, model_size="tiny"):
        return original_init(self, audio_path, model_size=model_size)
    monkeypatch.setattr(Transcriber, "__init__", mock_init)
    
    output_dir = os.path.join(temp_dir, "nested", "output")
    process_video(sample_video, output_dir)
    assert os.path.exists(output_dir)

@pytest.mark.integration
def test_pipeline_invalid_video(temp_dir, mock_anthropic):
    """Test pipeline handling of invalid video file."""
    with pytest.raises(FileNotFoundError):
        process_video("nonexistent.mp4", temp_dir)

@pytest.mark.integration
def test_pipeline_corrupted_video(temp_dir, mock_anthropic):
    """Test pipeline handling of corrupted video file."""
    # Create corrupted video file
    corrupt_video = os.path.join(temp_dir, "corrupt.mp4")
    with open(corrupt_video, "wb") as f:
        f.write(b"not a valid video file")
    
    with pytest.raises(Exception):
        process_video(corrupt_video, temp_dir)
