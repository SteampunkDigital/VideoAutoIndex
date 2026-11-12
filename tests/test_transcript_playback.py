import json
import shutil
import subprocess
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.web_generator import WebGenerator


def generate(tmp_path, chunks, speaker_segments=None, audio=False):
    analysis, video, transcript = (tmp_path / name for name in ("analysis.json", "audio.wav" if audio else "video.mp4", "transcript.json"))
    analysis.write_text("[]")
    video.touch()
    transcript.write_text(json.dumps({"chunks": chunks, "speaker_segments": speaker_segments or []}, ensure_ascii=False), encoding="utf-8")
    generator = WebGenerator(analysis, video, transcript)
    html_path = generator.generate(tmp_path)
    return generator, BeautifulSoup(Path(html_path).read_text(encoding="utf-8"), "html.parser")


def test_speaker_metadata_escaping_legacy_and_invalid_chunks(tmp_path):
    generator, soup = generate(tmp_path, [
        {"timestamp": [10, 14], "text": "質問 <script>alert(1)</script>", "speaker": 'A"<b>'},
        {"timestamp": [12, 16], "text": "回答", "speaker": "B"},
        {"timestamp": [16, 18], "text": "Unknown", "speaker": None},
        {"timestamp": [18, 20], "text": "Legacy"},
        {"timestamp": [None, 20], "text": "Invalid"},
        {"timestamp": [1, 0], "text": "Invalid"},
        {"timestamp": [float('nan'), 1], "text": "Invalid"},
    ])
    rows = soup.select(".transcript-chunk")
    assert len(rows) == 4
    assert all(row.name == "button" for row in rows)
    assert rows[0]["data-speaker"] == 'A"<b>'
    assert rows[0].select_one(".speaker-label").text == 'A"<b>'
    assert rows[0].find("script") is None and rows[0].find("b") is None
    assert "質問" in rows[0].text
    assert rows[1]["data-start"] == "12.0" and rows[1]["data-end"] == "16.0"
    assert rows[2].select_one(".speaker-label").text == "Unknown speaker"
    assert rows[3].select_one(".speaker-label") is None
    assert rows[0]["style"] != rows[1]["style"]
    assert generator._seconds_to_timestamp(59.9999) == "00:01:00,000"


@pytest.mark.skipif(shutil.which("node") is None, reason="Playback behavior tests require Node.js")
def test_actual_generated_javascript_highlights_all_active_rows(tmp_path):
    spans = [(10, 14, "A"), (12, 16, "B"), (12.5, 13, "C"), (14, 15, "A"),
             (16, 18, "A"), (16, 17, "A"), (18, 20, None), (18, 20, None)]
    _, soup = generate(tmp_path, [
        {"timestamp": [start, end], "speaker": speaker, "text": f"Segment {index}"}
        for index, (start, end, speaker) in enumerate(spans)
    ])
    rows = [{"start": row["data-start"], "end": row["data-end"], "speaker": row["data-speaker"]}
            for row in soup.select(".transcript-chunk")]
    result = subprocess.run(
        ["node", str(Path(__file__).with_name("transcript_playback.cjs"))],
        input=json.dumps({"script": soup.script.string, "rows": rows}),
        text=True, capture_output=True, check=True,
    )
    assert "passed" in result.stdout


def test_video_page_shows_all_phrases_without_a_speaker_activity_section(tmp_path):
    _, soup = generate(tmp_path, [
        {"timestamp": [10, 16], "speaker": "Speaker 1", "text": "First phrase"},
        {"timestamp": [12, 14], "speaker": "Speaker 2", "text": "Second phrase"},
        {"timestamp": [13, 15], "speaker": None, "text": "Unknown phrase"},
    ], speaker_segments=[
        {"timestamp": [10, 16], "speaker": "Speaker 1"},
        {"timestamp": [12, 14], "speaker": "Speaker 2"},
    ])
    assert soup.select_one('.speaker-activity') is None
    assert soup.select_one('.speaker-interval') is None
    assert soup.find('details') is None
    assert 'Detected speaker activity' not in soup.get_text()
    assert len(soup.select('.transcript-chunk')) == 3
    assert all(text in soup.get_text() for text in ['First phrase', 'Second phrase', 'Unknown phrase'])
    assert soup.video['id'] == 'meeting-video'
    assert '.transcript-chunk.overlapping' in soup.style.string


def test_audio_page_shows_phrases_with_playback_controls(tmp_path):
    _, soup = generate(tmp_path, [
        {"timestamp": [1, 4], "speaker": "Speaker 1", "text": "Audio phrase"},
    ], audio=True)
    assert soup.audio is not None
    assert soup.source['type'].startswith('audio/')
    assert len(soup.select('.transcript-chunk')) == 1
    assert soup.find('details') is None
