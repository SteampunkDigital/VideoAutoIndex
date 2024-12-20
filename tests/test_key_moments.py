import pytest
import os
import json
from src.key_moments import KeyMomentsExtractor

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
    class Content:
        def __init__(self, text):
            self.text = text
    
    return {
        "content": [Content(json.dumps(sample_analysis))]
    }

def test_key_moments_init(sample_srt, mock_anthropic_key):
    """Test KeyMomentsExtractor initialization with valid subtitle file."""
    extractor = KeyMomentsExtractor(sample_srt)
    assert extractor.subtitle_path == sample_srt

def test_key_moments_init_invalid_path(mock_anthropic_key):
    """Test KeyMomentsExtractor initialization with non-existent subtitle file."""
    with pytest.raises(FileNotFoundError):
        KeyMomentsExtractor("nonexistent.srt")

def test_validate_timestamp_format(sample_srt, mock_anthropic_key):
    """Test timestamp format validation."""
    extractor = KeyMomentsExtractor(sample_srt)
    
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
    extractor = KeyMomentsExtractor(sample_srt)
    
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
    class MockMessage:
        def __init__(self, content):
            self.content = mock_anthropic_response["content"]
    
    class MockAnthropicMessages:
        def create(self, **kwargs):
            return MockMessage(None)
    
    class MockAnthropic:
        def __init__(self, api_key):
            self.messages = MockAnthropicMessages()
    
    monkeypatch.setattr("src.key_moments.Anthropic", MockAnthropic)
    
    extractor = KeyMomentsExtractor(sample_srt)
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
def test_extract_key_moments_no_api_key(sample_srt):
    """Test key moments extraction fails without API key."""
    if "ANTHROPIC_API_KEY" in os.environ:
        del os.environ["ANTHROPIC_API_KEY"]
    
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY.*required"):
        KeyMomentsExtractor(sample_srt)

@pytest.mark.integration
def test_extract_key_moments_invalid_response(sample_srt, mock_anthropic_key, monkeypatch):
    """Test handling of invalid API responses."""
    class MockMessage:
        def __init__(self, content):
            self.content = [type('Content', (), {'text': 'invalid json'})()]
    
    class MockAnthropicMessages:
        def create(self, **kwargs):
            return MockMessage(None)
    
    class MockAnthropic:
        def __init__(self, api_key):
            self.messages = MockAnthropicMessages()
    
    monkeypatch.setattr("src.key_moments.Anthropic", MockAnthropic)
    
    extractor = KeyMomentsExtractor(sample_srt)
    with pytest.raises(Exception, match="Failed to parse API response"):
        extractor.extract_key_moments()
