import pytest
from src.key_moments import KeyMomentsExtractor

@pytest.mark.parametrize("timestamp,expected", [
    ("00:00:00,000", 0.0),
    ("00:00:01,000", 1.0),
    ("00:01:00,000", 60.0),
    ("01:00:00,000", 3600.0),
    ("00:00:00,500", 0.5),
    ("01:23:45,678", 5025.678),
])
def test_parse_timestamp(timestamp, expected, dummy_srt, mock_anthropic_key):
    """Test timestamp parsing with various formats."""
    extractor = KeyMomentsExtractor(dummy_srt)
    assert extractor._parse_timestamp(timestamp) == expected

@pytest.mark.parametrize("timestamp", [
    "00:00:00.000",  # Wrong separator
    "0:00:00,000",   # Missing leading zero
    "00:00:00,0",    # Missing milliseconds
    "100:00:00,000", # Hours too large
    "00:60:00,000",  # Minutes too large
    "00:00:60,000",  # Seconds too large
    "00:00:00,1000", # Milliseconds too large
    "00:00:00",      # Missing milliseconds
    "invalid",       # Completely invalid
])
def test_invalid_timestamp_format(timestamp, dummy_srt, mock_anthropic_key):
    """Test validation of invalid timestamp formats."""
    extractor = KeyMomentsExtractor(dummy_srt)
    with pytest.raises(ValueError):
        extractor._validate_timestamp_format(timestamp)
