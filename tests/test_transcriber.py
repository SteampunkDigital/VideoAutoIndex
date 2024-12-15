import pytest
import os
from src.transcriber import Transcriber

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

@pytest.mark.integration
def test_transcribe(sample_video, temp_dir):
    """Test full transcription pipeline with a sample video."""
    # First extract audio using VideoProcessor
    from src.video_processor import VideoProcessor
    processor = VideoProcessor(sample_video)
    audio_path = processor.extract_audio(temp_dir)
    
    # Then transcribe the audio
    transcriber = Transcriber(audio_path)
    subtitle_path = transcriber.transcribe(temp_dir)
    
    # Check that subtitle file was created
    assert os.path.exists(subtitle_path)
    assert subtitle_path.endswith(".srt")
    
    # Check subtitle file is not empty and has valid format
    with open(subtitle_path, 'r') as f:
        content = f.read()
        # Basic SRT format validation
        assert content.strip(), "Subtitle file is empty"
        lines = content.split('\n')
        assert len(lines) >= 4, "Subtitle file has invalid format"
        # Check first subtitle block format
        assert lines[0].isdigit(), "First line should be a number"
        assert '-->' in lines[1], "Second line should contain timestamp"
        assert lines[2], "Third line should contain text"

@pytest.mark.integration
def test_transcribe_creates_output_dir(sample_video, temp_dir):
    """Test transcription creates output directory if it doesn't exist."""
    # First extract audio
    from src.video_processor import VideoProcessor
    processor = VideoProcessor(sample_video)
    audio_path = processor.extract_audio(temp_dir)
    
    # Create a nested output path
    output_dir = os.path.join(temp_dir, "nested", "output")
    
    # Transcribe should create the directory
    transcriber = Transcriber(audio_path)
    subtitle_path = transcriber.transcribe(output_dir)
    
    assert os.path.exists(output_dir)
    assert os.path.exists(subtitle_path)

@pytest.mark.integration
def test_transcribe_invalid_audio(temp_dir):
    """Test transcription with invalid audio file."""
    # Create an invalid audio file
    invalid_audio = os.path.join(temp_dir, "invalid.wav")
    with open(invalid_audio, "wb") as f:
        f.write(b"not a valid wav file")
    
    transcriber = Transcriber(invalid_audio)
    with pytest.raises(Exception):
        transcriber.transcribe(temp_dir)
