import pytest
import os
import json
import subprocess
from pathlib import Path
from src.main import process_video, check_ffmpeg, check_python_dependencies, check_api_key, create_transcriber, get_api_config

@pytest.fixture
def test_data_dir():
    """Get the test_data directory path."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_data")

@pytest.fixture
def sample_analysis(test_data_dir):
    """Load the actual test data analysis."""
    analysis_path = os.path.join(test_data_dir, "meeting_analysis.json")
    with open(analysis_path, 'r') as f:
        return json.load(f)

@pytest.fixture
def mock_anthropic_response(sample_analysis):
    """Mock Anthropic API response using actual test data."""
    return {
        "content": json.dumps(sample_analysis)
    }

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
        if name == "ffmpeg":  # Test for one of the actual dependencies
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

def test_get_api_config_apple_does_not_require_key():
    """Test Apple Foundation Models selection does not require an API key."""
    class Args:
        apple = True
        anthropic = None
        openai = None

    assert get_api_config(Args()) == ("apple", None)

def test_create_transcriber_defaults_to_whisper(dummy_wav):
    """Test default transcriber selection uses Whisper compatibility path."""
    transcriber = create_transcriber(dummy_wav)

    assert transcriber.__class__.__name__ == "Transcriber"

def test_create_transcriber_qwen(dummy_wav):
    """Test qwen transcriber selection uses Canary-Qwen CoreML class."""
    transcriber = create_transcriber(dummy_wav, "qwen")

    assert transcriber.__class__.__name__ == "CanaryQwenCoreMLTranscriber"

def test_create_transcriber_dictation(dummy_wav):
    """Test dictation transcriber selection uses Apple Speech wrapper."""
    transcriber = create_transcriber(dummy_wav, "dictation")

    assert transcriber.__class__.__name__ == "AppleDictationTranscriber"

def test_create_transcriber_invalid_name(dummy_wav):
    """Test invalid transcriber selection fails clearly."""
    with pytest.raises(ValueError, match="transcriber_name"):
        create_transcriber(dummy_wav, "invalid")

@pytest.mark.xfail(reason="Anthropic API mocking needs to be fixed")
@pytest.mark.integration
def test_full_pipeline(sample_video, temp_dir, monkeypatch, test_data_dir):
    """Test the complete video processing pipeline."""
    # Use base model for testing
    from src.transcriber import Transcriber
    original_init = Transcriber.__init__
    def mock_init(self, audio_path, model_name="openai/whisper-base"):
        return original_init(self, audio_path, model_name)
    monkeypatch.setattr(Transcriber, "__init__", mock_init)
    
    process_video(sample_video, temp_dir)
    
    # Check that all expected output files were created with correct names
    expected_files = [
        "audio_transcript.json",
        "audio_subtitles.srt",
        "meeting_analysis.json"
    ]
    
    for filename in expected_files:
        file_path = os.path.join(temp_dir, filename)
        assert os.path.exists(file_path), f"Missing output file: {filename}"
        
        # Compare with test data structure if it's a JSON file
        if filename.endswith('.json'):
            with open(file_path, 'r') as f:
                output = json.load(f)
            with open(os.path.join(test_data_dir, filename), 'r') as f:
                test_data = json.load(f)
                
            # Check structure matches (not exact content since it's generated)
            if filename == "audio_transcript.json":
                assert "speakers" in output
                assert "chunks" in output
                assert "text" in output
            elif filename == "meeting_analysis.json":
                assert len(output) > 0
                topic = output[0]
                assert all(key in topic for key in ["topic", "timestamp", "key_moments", "takeaways"])
    
    # Check HTML summary
    html_files = list(Path(temp_dir).glob("*_summary.html"))
    assert len(html_files) > 0, "Missing HTML summary file"
    
    with open(html_files[0], 'r') as f:
        content = f.read()
        assert "Meeting Summary" in content
        assert "video" in content.lower()
        assert "timestamp" in content.lower()
        assert "key-moment" in content.lower()
        assert "takeaway" in content.lower()

@pytest.mark.xfail(reason="Anthropic API mocking needs to be fixed")
@pytest.mark.integration
def test_pipeline_creates_output_dir(sample_video, temp_dir, monkeypatch):
    """Test that the pipeline creates nested output directories."""
    # Use base model for testing
    from src.transcriber import Transcriber
    original_init = Transcriber.__init__
    def mock_init(self, audio_path, model_name="openai/whisper-base"):
        return original_init(self, audio_path, model_name)
    monkeypatch.setattr(Transcriber, "__init__", mock_init)
    
    output_dir = os.path.join(temp_dir, "nested", "output")
    process_video(sample_video, output_dir)
    assert os.path.exists(output_dir)

@pytest.mark.integration
def test_pipeline_invalid_video(temp_dir):
    """Test pipeline handling of invalid video file."""
    with pytest.raises(FileNotFoundError):
        process_video("nonexistent.mp4", temp_dir)

@pytest.mark.integration
def test_pipeline_corrupted_video(temp_dir):
    """Test pipeline handling of corrupted video file."""
    # Create corrupted video file
    corrupt_video = os.path.join(temp_dir, "corrupt.mp4")
    with open(corrupt_video, "wb") as f:
        f.write(b"not a valid video file")
    
    with pytest.raises(Exception):
        process_video(corrupt_video, temp_dir)
