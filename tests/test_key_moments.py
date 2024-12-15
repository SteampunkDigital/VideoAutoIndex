import pytest
import os
import json
from src.key_moments import KeyMomentsExtractor

@pytest.fixture
def sample_srt(temp_dir):
    """Create a sample SRT file for testing."""
    srt_content = """1
00:00:00,000 --> 00:00:05,000
Welcome to our project meeting.

2
00:00:05,000 --> 00:00:10,000
Today we'll discuss the roadmap and budget.

3
00:00:10,000 --> 00:00:15,000
First, let's review our progress.

4
00:00:15,000 --> 00:00:20,000
We've completed phase one ahead of schedule.
"""
    srt_path = os.path.join(temp_dir, "test.srt")
    with open(srt_path, "w") as f:
        f.write(srt_content)
    return srt_path

def test_key_moments_init(sample_srt):
    """Test KeyMomentsExtractor initialization with valid subtitle file."""
    extractor = KeyMomentsExtractor(sample_srt)
    assert extractor.subtitle_path == sample_srt

def test_key_moments_init_invalid_path():
    """Test KeyMomentsExtractor initialization with non-existent subtitle file."""
    with pytest.raises(FileNotFoundError):
        KeyMomentsExtractor("nonexistent.srt")

def test_validate_timestamp_format():
    """Test timestamp format validation."""
    extractor = KeyMomentsExtractor("dummy.srt")  # Path doesn't matter for this test
    
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

def test_parse_timestamp():
    """Test timestamp parsing to seconds."""
    extractor = KeyMomentsExtractor("dummy.srt")  # Path doesn't matter for this test
    
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
def test_extract_key_moments(sample_srt, monkeypatch):
    """Test key moments extraction with mocked Anthropic API."""
    # Mock Anthropic API response
    mock_response = {
        "content": json.dumps([
            {
                "topic": "Meeting Introduction",
                "timestamp": "00:00:00,000",
                "key_moments": [
                    {
                        "description": "Meeting agenda outlined",
                        "timestamp": "00:00:05,000"
                    }
                ],
                "takeaways": [
                    "Review roadmap and budget",
                    "Discuss project progress"
                ]
            }
        ])
    }
    
    class MockMessage:
        def __init__(self, content):
            self.content = content
    
    class MockAnthropicMessages:
        def create(self, **kwargs):
            return MockMessage(mock_response["content"])
    
    class MockAnthropic:
        def __init__(self, api_key):
            self.messages = MockAnthropicMessages()
    
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy_key")
    monkeypatch.setattr("src.key_moments.Anthropic", MockAnthropic)
    
    # Test extraction
    extractor = KeyMomentsExtractor(sample_srt)
    result = extractor.extract_key_moments()
    
    # Validate result structure
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
def test_extract_key_moments_invalid_response(sample_srt, monkeypatch):
    """Test handling of invalid API responses."""
    class MockMessage:
        def __init__(self, content):
            self.content = content
    
    class MockAnthropicMessages:
        def create(self, **kwargs):
            return MockMessage("invalid json")
    
    class MockAnthropic:
        def __init__(self, api_key):
            self.messages = MockAnthropicMessages()
    
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy_key")
    monkeypatch.setattr("src.key_moments.Anthropic", MockAnthropic)
    
    extractor = KeyMomentsExtractor(sample_srt)
    with pytest.raises(Exception, match="Failed to parse.*response"):
        extractor.extract_key_moments()