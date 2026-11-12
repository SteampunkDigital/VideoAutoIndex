import pytest
import os
import json
from pathlib import Path
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
    assert extractor.source_path.name == "main.swift"
    assert extractor.source_path.parent.name == "AppleFoundationKeyMoments"
    assert extractor.info_plist_path.name == "Info.plist"
    assert extractor.info_plist_path.parent.name == "AppleFoundationKeyMoments"
    assert extractor.binary_path.name == "apple_foundation_key_moments"
    assert extractor.anthropic is None
    assert extractor.openai is None

def test_key_moments_sdk_roots_include_xcode_beta():
    import src.key_moments as key_moments

    assert Path("/Applications/Xcode-beta.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs") in key_moments.MACOS_SDK_ROOTS

def test_key_moments_prompt_translates_output_to_english(sample_srt, mock_anthropic_key, mock_anthropic_response, monkeypatch):
    """Test cloud analysis prompts translate non-English transcript content into English output."""
    captured = {}

    class MockAnthropicStream:
        def __enter__(self):
            self.text_stream = [mock_anthropic_response]
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class MockAnthropicMessages:
        def stream(self, **kwargs):
            captured.update(kwargs)
            return MockAnthropicStream()

    class MockAnthropic:
        def __init__(self, api_key):
            self.messages = MockAnthropicMessages()

    monkeypatch.setattr("src.key_moments.Anthropic", MockAnthropic)

    extractor = KeyMomentsExtractor(sample_srt, api_provider="anthropic", api_key="test-key")
    extractor.extract_key_moments()

    prompt = captured["messages"][0]["content"]
    assert "Write all JSON" in prompt
    assert "string values in English" in prompt
    assert "Translate topic names, key moment descriptions, and takeaways into English" in prompt
    assert "Do not translate or alter timestamp strings" in prompt
    assert "Overlapping cue time ranges represent simultaneous speech" in prompt
    assert "do not infer identity across parts" in prompt
    assert "uncertain or unknown speaker" in prompt
    assert "Translate non-English transcript content into English" in captured["system"]


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_summary_model_override_reaches_request(provider, sample_srt, monkeypatch, sample_analysis):
    from types import SimpleNamespace
    from unittest.mock import Mock
    client = Mock()
    if provider == "anthropic":
        client.messages = SimpleNamespace(create=Mock(return_value=SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(sample_analysis))])))
        monkeypatch.setattr("src.key_moments.Anthropic", Mock(return_value=client))
    else:
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(sample_analysis)))])
        monkeypatch.setattr("src.key_moments.OpenAI", Mock(return_value=client))
    extractor = KeyMomentsExtractor(sample_srt, api_provider=provider,
                                    api_key="test-key", model_name="chosen-summary-model")
    extractor.extract_key_moments()
    request = client.messages.create if provider == "anthropic" else client.chat.completions.create
    assert request.call_args.kwargs["model"] == "chosen-summary-model"

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


def test_validate_topics_normalizes_srt_timestamp_ranges(sample_srt, mock_anthropic_key):
    """Test model-produced SRT ranges are normalized to start timestamps."""
    extractor = KeyMomentsExtractor(sample_srt, api_provider="anthropic", api_key="test-key")
    topics = [
        {
            "topic": "Hybrid battery condition",
            "timestamp": "00:00:00,000 --> 00:00:23,460",
            "key_moments": [
                {
                    "description": "The battery status is discussed.",
                    "timestamp": "00:00:15,540 --> 00:00:16,740",
                }
            ],
            "takeaways": ["Battery state appears acceptable."],
        }
    ]

    extractor._validate_topics(topics)

    assert topics[0]["timestamp"] == "00:00:00,000"
    assert topics[0]["key_moments"][0]["timestamp"] == "00:00:15,540"


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
