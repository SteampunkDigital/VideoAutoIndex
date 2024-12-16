import pytest
import os
import json
from src.transcriber import Transcriber

@pytest.fixture
def test_data_dir():
    """Get the test_data directory path."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_data")

@pytest.fixture
def sample_transcript(test_data_dir):
    """Load the actual test data transcript."""
    transcript_path = os.path.join(test_data_dir, "audio_transcript.json")
    with open(transcript_path, 'r') as f:
        return json.load(f)

@pytest.fixture
def sample_subtitles(test_data_dir):
    """Load the actual test data subtitles."""
    subtitle_path = os.path.join(test_data_dir, "audio_subtitles.srt")
    with open(subtitle_path, 'r') as f:
        return f.read()

def test_transcriber_init(temp_dir):
    """Test Transcriber initialization with valid audio file."""
    # Create a dummy audio file
    audio_path = os.path.join(temp_dir, "test_audio.wav")
    with open(audio_path, "wb") as f:
        f.write(b"dummy audio data")
    
    transcriber = Transcriber(audio_path)
    assert transcriber.audio_path == audio_path

def test_transcriber_init_invalid_path():
    """Test Transcriber initialization with non-existent audio file."""
    with pytest.raises(FileNotFoundError):
        Transcriber("nonexistent_audio.wav")

def test_format_timestamp():
    """Test timestamp formatting."""
    transcriber = Transcriber("dummy.wav")  # Path doesn't matter for this test
    
    test_cases = [
        (0.0, "00:00:00,000"),
        (1.0, "00:00:01,000"),
        (60.0, "00:01:00,000"),
        (3600.0, "01:00:00,000"),
        (0.5, "00:00:00,500"),
        (5025.678, "01:23:45,678"),
    ]
    
    for seconds, expected in test_cases:
        assert transcriber._format_timestamp(seconds) == expected

def test_json_to_srt(temp_dir, sample_transcript, sample_subtitles):
    """Test JSON to SRT conversion using actual test data."""
    transcriber = Transcriber("dummy.wav")  # Path doesn't matter for this test
    
    # Write sample transcript to temp file
    json_path = os.path.join(temp_dir, "test_transcript.json")
    with open(json_path, 'w') as f:
        json.dump(sample_transcript, f)
    
    # Convert to SRT
    srt_path = os.path.join(temp_dir, "test.srt")
    transcriber._json_to_srt(json_path, srt_path)
    
    # Read generated SRT
    with open(srt_path, 'r') as f:
        generated_srt = f.read()
    
    # Compare with sample subtitles
    # Normalize line endings and whitespace for comparison
    assert generated_srt.strip().replace('\r\n', '\n') == sample_subtitles.strip().replace('\r\n', '\n')

@pytest.mark.integration
def test_transcribe(sample_video, temp_dir):
    """Test full transcription pipeline with a sample video."""
    # First extract audio using VideoProcessor
    from src.video_processor import VideoProcessor
    processor = VideoProcessor(sample_video)
    audio_path = processor.extract_audio(temp_dir)
    
    # Then transcribe the audio
    transcriber = Transcriber(audio_path)
    transcript_path = os.path.join(temp_dir, "audio_transcript.json")
    subtitle_path = os.path.join(temp_dir, "audio_subtitles.srt")
    transcriber.transcribe(transcript_path, subtitle_path)
    
    # Verify transcript JSON format matches test data structure
    with open(transcript_path, 'r') as f:
        transcript = json.load(f)
        assert "speakers" in transcript
        assert "chunks" in transcript
        assert "text" in transcript
        assert isinstance(transcript["chunks"], list)
        for chunk in transcript["chunks"]:
            assert "timestamp" in chunk
            assert "text" in chunk
            assert isinstance(chunk["timestamp"], list)
            assert len(chunk["timestamp"]) == 2

    # Verify SRT file exists and has content
    assert os.path.exists(subtitle_path)
    with open(subtitle_path, 'r') as f:
        content = f.read()
        assert content.strip()
        # Basic SRT format validation
        lines = content.split('\n')
        assert len(lines) >= 4
        assert lines[0].isdigit()  # First line should be a number
        assert '-->' in lines[1]   # Second line should contain timestamp
        assert lines[2]            # Third line should contain text

@pytest.mark.integration
def test_transcribe_creates_output_dir(sample_video, temp_dir):
    """Test transcription creates output directory if it doesn't exist."""
    # First extract audio
    from src.video_processor import VideoProcessor
    processor = VideoProcessor(sample_video)
    audio_path = processor.extract_audio(temp_dir)
    
    # Create a nested output path
    output_dir = os.path.join(temp_dir, "nested", "output")
    transcript_path = os.path.join(output_dir, "audio_transcript.json")
    subtitle_path = os.path.join(output_dir, "audio_subtitles.srt")
    
    # Transcribe should create the directory
    transcriber = Transcriber(audio_path)
    transcriber.transcribe(transcript_path, subtitle_path)
    
    assert os.path.exists(output_dir)
    assert os.path.exists(transcript_path)
    assert os.path.exists(subtitle_path)

@pytest.mark.integration
def test_transcribe_invalid_audio(temp_dir):
    """Test transcription with invalid audio file."""
    # Create an invalid audio file
    invalid_audio = os.path.join(temp_dir, "invalid.wav")
    with open(invalid_audio, "wb") as f:
        f.write(b"not a valid wav file")
    
    transcriber = Transcriber(invalid_audio)
    transcript_path = os.path.join(temp_dir, "audio_transcript.json")
    subtitle_path = os.path.join(temp_dir, "audio_subtitles.srt")
    
    with pytest.raises(Exception):
        transcriber.transcribe(transcript_path, subtitle_path)
