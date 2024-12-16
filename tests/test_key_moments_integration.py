import pytest
import os
import json
from src.key_moments import KeyMomentsExtractor

@pytest.mark.integration
def test_key_moments_with_sample_transcript(temp_dir):
    """Test key moments extraction with a real sample transcript."""
    # Create a realistic sample transcript
    transcript_content = """1
00:00:00,000 --> 00:00:05,000
Hello everyone, welcome to our quarterly planning meeting.

2
00:00:05,000 --> 00:00:10,000
Today we'll discuss our Q4 goals and strategy.

3
00:00:10,000 --> 00:00:15,000
First, let's review our Q3 performance.

4
00:00:15,000 --> 00:00:20,000
We exceeded our targets by 15% across all metrics.
"""
    
    transcript_path = os.path.join(temp_dir, "sample_transcript.srt")
    with open(transcript_path, "w") as f:
        f.write(transcript_content)
    
    extractor = KeyMomentsExtractor(transcript_path)
    analysis = extractor.extract_key_moments()
    
    # Validate analysis structure and content
    assert isinstance(analysis, list)
    assert len(analysis) > 0
    
    for topic in analysis:
        assert "topic" in topic
        assert "timestamp" in topic
        assert "key_moments" in topic
        assert "takeaways" in topic
        
        # Validate timestamp formats
        assert _is_valid_timestamp(topic["timestamp"])
        for moment in topic["key_moments"]:
            assert _is_valid_timestamp(moment["timestamp"])
            assert moment["description"].strip() != ""
        
        # Validate takeaways
        assert len(topic["takeaways"]) > 0
        for takeaway in topic["takeaways"]:
            assert takeaway.strip() != ""

def _is_valid_timestamp(timestamp):
    """Helper function to validate SRT timestamp format."""
    import re
    pattern = r'^\d{2}:\d{2}:\d{2},\d{3}$'
    return bool(re.match(pattern, timestamp))

@pytest.mark.integration
def test_key_moments_with_long_transcript(temp_dir):
    """Test key moments extraction with a longer transcript to test performance."""
    # Create a longer transcript (5 minutes)
    lines = []
    for i in range(60):  # 5 seconds per subtitle = 60 subtitles for 5 minutes
        start_time = f"{i//12:02d}:{(i%12)*5:02d}:00,000"
        end_time = f"{i//12:02d}:{(i%12)*5+5:02d}:00,000"
        lines.extend([
            str(i+1),
            f"{start_time} --> {end_time}",
            f"This is subtitle number {i+1} with some discussion content.",
            ""
        ])
    
    transcript_path = os.path.join(temp_dir, "long_transcript.srt")
    with open(transcript_path, "w") as f:
        f.write("\n".join(lines))
    
    extractor = KeyMomentsExtractor(transcript_path)
    analysis = extractor.extract_key_moments()
    
    # Validate analysis
    assert isinstance(analysis, list)
    assert len(analysis) > 0

@pytest.mark.integration
def test_key_moments_with_special_characters(temp_dir):
    """Test key moments extraction with special characters and formatting."""
    transcript_content = """1
00:00:00,000 --> 00:00:05,000
Let's discuss the $500K budget & 15% growth target.

2
00:00:05,000 --> 00:00:10,000
Project "Alpha" launches in Q4 2023!

3
00:00:10,000 --> 00:00:15,000
Email john.doe@company.com for details.
"""
    
    transcript_path = os.path.join(temp_dir, "special_chars.srt")
    with open(transcript_path, "w") as f:
        f.write(transcript_content)
    
    extractor = KeyMomentsExtractor(transcript_path)
    analysis = extractor.extract_key_moments()
    
    assert isinstance(analysis, list)
    assert len(analysis) > 0
