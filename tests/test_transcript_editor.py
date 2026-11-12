import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup

from src.web_generator import WebGenerator


def test_feedback_contains_original_source_and_stable_phrase_anchors(tmp_path):
    analysis, video, transcript = [tmp_path / name for name in ('analysis.json', 'meeting.mp4', 'transcript.json')]
    analysis.write_text('[]')
    video.touch()
    source = json.dumps({
        'metadata': {'backend': 'speechcpp', 'model': 'nemotron-3.5-transcribe'},
        'chunks': [
            {'id': 'phrase-3', 'timestamp': [13.215, 15.356], 'speaker': 'Speaker 2',
             'text': "And that's why the decorative button was not working."},
            {'id': 'phrase-4', 'timestamp': [14, 16], 'speaker': None, 'text': 'Unknown voice'},
        ],
    }, ensure_ascii=False).encode()
    transcript.write_bytes(source)
    page = WebGenerator(analysis, video, transcript).generate(tmp_path)
    soup = BeautifulSoup(Path(page).read_text(), 'html.parser')
    data = json.loads(soup.select_one('#transcript-editor-data').string)
    assert data['source']['transcript_sha256'] == hashlib.sha256(source).hexdigest()
    assert data['source']['model'] == 'nemotron-3.5-transcribe'
    assert data['source']['media_file'] == 'meeting.mp4'
    assert data['phrases'][0]['segment_id'] == 'phrase-3'
    assert data['phrases'][0]['start_seconds'] == 13.215
    assert data['phrases'][0]['speaker_id'] == 'Speaker 2'
    assert data['phrases'][0]['text'].startswith("And that's why the decorative")
    assert data['phrases'][1]['speaker_id'] is None
    assert soup.select_one('#corrections-json').has_attr('readonly')
    assert soup.select_one('.speaker-chip')['aria-readonly'] == 'true'
    assert len(soup.select('.speaker-chip')) == 1
    assert len(soup.select('.phrase-text')) == 2
    assert 'localStorage' not in soup.select_one('script:not([type])').string
    assert 'sessionStorage' not in soup.select_one('script:not([type])').string


def test_embedded_feedback_and_phrase_text_cannot_inject_markup(tmp_path):
    analysis, video, transcript = [tmp_path / name for name in ('analysis.json', 'meeting.mp4', 'transcript.json')]
    analysis.write_text('[]')
    video.touch()
    malicious = '</script><script>window.injected = true</script>'
    transcript.write_text(json.dumps({'chunks': [
        {'timestamp': [0, 2], 'speaker': malicious, 'text': malicious},
    ]}))
    page = WebGenerator(analysis, video, transcript).generate(tmp_path)
    soup = BeautifulSoup(Path(page).read_text(), 'html.parser')
    data = json.loads(soup.select_one('#transcript-editor-data').string)
    assert data['phrases'][0]['text'] == malicious
    assert soup.select_one('.phrase-text').text == malicious
    assert len(soup.find_all('script')) == 2
    assert not soup.select_one('.transcript-chunk').find('script')
