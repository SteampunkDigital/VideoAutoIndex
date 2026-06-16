import pytest
import os
import json
from src.key_moments import DEFAULT_OPENAI_MODEL, KeyMomentsExtractor

@pytest.fixture
def mock_anthropic_key(monkeypatch):
    """Mock Anthropic API key for testing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

@pytest.fixture
def test_data_dir():
    """Get the test_data directory path."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_data")

@pytest.fixture
def sample_srt(test_data_dir):
    """Use the actual test data SRT file."""
    return os.path.join(test_data_dir, "audio_subtitles.srt")

@pytest.fixture
def sample_analysis(test_data_dir):
    """Load the actual test data analysis."""
    analysis_path = os.path.join(test_data_dir, "meeting_analysis.json")
    with open(analysis_path, 'r') as f:
        return json.load(f)

@pytest.fixture
def mock_anthropic_response(sample_analysis):
    """Mock Anthropic API response using actual test data."""
    return json.dumps(sample_analysis)

def test_key_moments_init(sample_srt, mock_anthropic_key):
    """Test KeyMomentsExtractor initialization with valid subtitle file."""
    extractor = KeyMomentsExtractor(sample_srt, api_provider="anthropic", api_key="test-key")
    assert extractor.subtitle_path == sample_srt
    assert extractor.api_provider == "anthropic"

def test_key_moments_init_invalid_path(mock_anthropic_key):
    """Test KeyMomentsExtractor initialization with non-existent subtitle file."""
    with pytest.raises(FileNotFoundError):
        KeyMomentsExtractor("nonexistent.srt", api_provider="anthropic", api_key="test-key")

def test_key_moments_openai_uses_default_model(sample_srt, monkeypatch):
    """Test OpenAI initialization uses the current default model."""
    class MockOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key

    monkeypatch.setattr("src.key_moments.OpenAI", MockOpenAI)

    extractor = KeyMomentsExtractor(sample_srt, api_provider="openai", api_key="test-key")
    assert extractor.openai_model == DEFAULT_OPENAI_MODEL

def test_key_moments_apple_init_does_not_require_api_key(sample_srt, monkeypatch):
    """Test Apple Foundation Models initialization avoids cloud API clients."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    extractor = KeyMomentsExtractor(sample_srt, api_provider="apple")

    assert extractor.api_provider == "apple"
    assert extractor.source_path.name == "apple_foundation_key_moments.swift"
    assert extractor.info_plist_path.name == "apple_foundation_key_moments_Info.plist"
    assert extractor.binary_path.name == "apple_foundation_key_moments"
    assert extractor.anthropic is None
    assert extractor.openai is None

def test_validate_timestamp_format(sample_srt, mock_anthropic_key):
    """Test timestamp format validation."""
    extractor = KeyMomentsExtractor(sample_srt, api_provider="anthropic", api_key="test-key")
    
    # Valid timestamps
    extractor._validate_timestamp_format("00:00:00,000")
    extractor._validate_timestamp_format("01:23:45,678")
    extractor._validate_timestamp_format("99:59:59,999")
    
    # Invalid timestamps
    invalid_timestamps = [
        "00:00:00.000",  # Wrong separator
        "0:00:00,000",   # Missing leading zero
        "00:00:00,0",    # Missing milliseconds
        "100:00:00,000", # Hours too large
        "00:60:00,000",  # Minutes too large
        "00:00:60,000",  # Seconds too large
        "00:00:00,1000", # Milliseconds too large
        "00:00:00",      # Missing milliseconds
        "invalid",       # Completely invalid
    ]
    
    for timestamp in invalid_timestamps:
        with pytest.raises(ValueError):
            extractor._validate_timestamp_format(timestamp)

def test_parse_timestamp(sample_srt, mock_anthropic_key):
    """Test timestamp parsing to seconds."""
    extractor = KeyMomentsExtractor(sample_srt, api_provider="anthropic", api_key="test-key")
    
    test_cases = [
        ("00:00:00,000", 0.0),
        ("00:00:01,000", 1.0),
        ("00:01:00,000", 60.0),
        ("01:00:00,000", 3600.0),
        ("00:00:00,500", 0.5),
        ("01:23:45,678", 5025.678),
    ]
    
    for timestamp, expected in test_cases:
        assert extractor._parse_timestamp(timestamp) == expected

@pytest.mark.integration
def test_extract_key_moments(sample_srt, mock_anthropic_key, mock_anthropic_response, monkeypatch):
    """Test key moments extraction with mocked API using real test data."""
    class MockAnthropicStream:
        def __enter__(self):
            self.text_stream = [mock_anthropic_response]
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False
    
    class MockAnthropicMessages:
        def stream(self, **kwargs):
            return MockAnthropicStream()
    
    class MockAnthropic:
        def __init__(self, api_key):
            self.messages = MockAnthropicMessages()
    
    monkeypatch.setattr("src.key_moments.Anthropic", MockAnthropic)
    
    extractor = KeyMomentsExtractor(sample_srt, api_provider="anthropic", api_key="test-key")
    result = extractor.extract_key_moments()
    
    # Compare with actual test data structure
    assert isinstance(result, list)
    assert len(result) > 0
    
    topic = result[0]
    assert "topic" in topic
    assert "timestamp" in topic
    assert "key_moments" in topic
    assert "takeaways" in topic
    
    # Validate timestamp formats
    extractor._validate_timestamp_format(topic["timestamp"])
    for moment in topic["key_moments"]:
        assert "description" in moment
        assert "timestamp" in moment
        extractor._validate_timestamp_format(moment["timestamp"])

@pytest.mark.integration
def test_key_moments_invalid_provider(sample_srt):
    """Test initialization fails with an invalid provider."""
    with pytest.raises(ValueError, match="api_provider must be 'anthropic', 'openai', or 'apple'"):
        KeyMomentsExtractor(sample_srt, api_provider="invalid", api_key="test-key")

@pytest.mark.integration
def test_extract_key_moments_invalid_response(sample_srt, mock_anthropic_key, monkeypatch):
    """Test handling of invalid API responses."""
    class MockAnthropicStream:
        def __enter__(self):
            self.text_stream = ["invalid json"]
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False
    
    class MockAnthropicMessages:
        def stream(self, **kwargs):
            return MockAnthropicStream()
    
    class MockAnthropic:
        def __init__(self, api_key):
            self.messages = MockAnthropicMessages()
    
    monkeypatch.setattr("src.key_moments.Anthropic", MockAnthropic)
    
    extractor = KeyMomentsExtractor(sample_srt, api_provider="anthropic", api_key="test-key")
    with pytest.raises(Exception, match="Failed to parse API response"):
        extractor.extract_key_moments()

def test_extract_key_moments_apple_runs_swift_helper(sample_srt, sample_analysis, monkeypatch):
    """Test Apple provider delegates analysis to the Swift helper binary."""
    captured = {}

    def mock_run(command, check, capture_output, text):
        captured["command"] = command
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["text"] = text
        output_path = command[command.index("--output") + 1]
        with open(output_path, "w") as f:
            json.dump(sample_analysis, f)
        return None

    extractor = KeyMomentsExtractor(sample_srt, api_provider="apple")
    monkeypatch.setattr(extractor, "_ensure_binary", lambda: None)
    monkeypatch.setattr("src.key_moments.subprocess.run", mock_run)

    result = extractor.extract_key_moments()

    assert result == sample_analysis
    assert captured["command"][:3] == [str(extractor.binary_path), "--srt", sample_srt]
    assert "--output" in captured["command"]
    assert captured["check"] is True
    assert captured["capture_output"] is True
    assert captured["text"] is True
