import copy
import hashlib
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.transcript_feedback import apply_feedback, import_feedback
from src.web_generator import WebGenerator


@pytest.fixture
def review_case():
    data = {'speakers': ['Speaker 1', 'Speaker 2'], 'metadata': {'backend': 'speechcpp'},
            'chunks': [
                {'id': 'phrase-3', 'timestamp': [13.215, 15.356], 'speaker': 'Speaker 2',
                 'text': "And that's why the decorative button was not working."},
                {'id': 'phrase-4', 'timestamp': [14, 16], 'speaker': 'Speaker 1', 'text': 'Another voice.'},
            ]}
    source = json.dumps(data).encode()
    feedback = {
        'schema_version': 1, 'type': 'video-auto-index.transcript-feedback',
        'source': {'media_file': 'meeting.mp4', 'transcript_sha256': hashlib.sha256(source).hexdigest()},
        'speakers': [{'speaker_id': 'Speaker 1', 'name': 'Reviewer One'},
                     {'speaker_id': 'Speaker 2', 'name': 'Reviewer Two'}],
        'regions': [{'segment_id': 'phrase-3', 'start_seconds': 13.215, 'end_seconds': 15.356,
                     'speaker_id': 'Speaker 2', 'speaker_name': 'Reviewer Two',
                     'original_text': data['chunks'][0]['text'],
                     'corrected_text': "And that's why the Data Record button was not working.",
                     'word_hints': [{'original': 'decorative', 'replacement': 'Data Record'}]}],
    }
    return source, feedback


def test_applies_confirmed_edits_without_changing_stable_ids_or_times(review_case):
    source, feedback = review_case
    data = apply_feedback(source, feedback, 'meeting.mp4')
    assert data['speaker_names'] == {'Speaker 1': 'Reviewer One', 'Speaker 2': 'Reviewer Two'}
    assert data['chunks'][0]['speaker'] == 'Speaker 2'
    assert data['chunks'][0]['timestamp'] == [13.215, 15.356]
    assert 'Data Record button' in data['chunks'][0]['text']
    assert 'decorative button' in json.loads(source)['chunks'][0]['text']
    assert data['metadata']['review']['source_transcript_sha256'] == hashlib.sha256(source).hexdigest()
    assert 'Data Record button' in data['text']


@pytest.mark.parametrize('change', ['hash', 'media', 'timestamp', 'text', 'speaker', 'alias', 'id', 'duplicate', 'version'])
def test_invalid_feedback_is_rejected(review_case, change):
    source, feedback = review_case
    if change == 'hash': feedback['source']['transcript_sha256'] = '0' * 64
    if change == 'media': feedback['source']['media_file'] = 'other.mp4'
    if change == 'timestamp': feedback['regions'][0]['start_seconds'] = 13
    if change == 'text': feedback['regions'][0]['original_text'] = 'Unexpected text'
    if change == 'speaker': feedback['regions'][0]['speaker_id'] = 'Speaker 1'
    if change == 'alias': feedback['regions'][0]['speaker_name'] = 'Wrong name'
    if change == 'id': feedback['regions'][0]['segment_id'] = 'missing'
    if change == 'duplicate': feedback['regions'].append(copy.deepcopy(feedback['regions'][0]))
    if change == 'version': feedback['schema_version'] = 2
    with pytest.raises(ValueError): apply_feedback(source, feedback, 'meeting.mp4')


def test_empty_correction_removes_the_phrase(review_case):
    source, feedback = review_case
    feedback['regions'][0]['corrected_text'] = ''
    data = apply_feedback(source, feedback, 'meeting.mp4')
    assert [c['id'] for c in data['chunks']] == ['phrase-4']


def test_import_outputs_named_srt_and_html_without_overwriting_original(review_case, tmp_path):
    source, feedback = review_case
    transcript = tmp_path / 'audio_transcript.json'
    transcript.write_bytes(source)
    path = tmp_path / 'feedback.json'
    path.write_text(json.dumps(feedback))
    reviewed, subtitles = import_feedback(tmp_path, path, 'meeting.mp4')
    assert transcript.read_bytes() == source
    assert '[Reviewer Two]' in Path(subtitles).read_text()
    analysis, media = tmp_path / 'analysis.json', tmp_path / 'meeting.mp4'
    analysis.write_text('[]'); media.touch()
    page = WebGenerator(analysis, media, reviewed).generate(tmp_path)
    soup = BeautifulSoup(Path(page).read_text(), 'html.parser')
    assert soup.select_one('.speaker-chip').text == 'Reviewer Two'
    assert soup.select_one('.speaker-chip')['data-speaker-id'] == 'Speaker 2'
    embedded = json.loads(soup.select_one('#transcript-editor-data').string)
    assert embedded['phrases'][0]['speaker_name'] == 'Reviewer Two'
    assert embedded['source']['transcript_sha256'] != feedback['source']['transcript_sha256']
    assert embedded['phrases'][0]['text'] == feedback['regions'][0]['corrected_text']
    # A subsequent export can refer to this reviewed transcript rather than the original.
    second = copy.deepcopy(feedback)
    second['source'] = embedded['source']
    second['regions'] = []
    path.write_text(json.dumps(second))
    import_feedback(tmp_path, path, 'meeting.mp4')


def test_wrong_fingerprint_does_not_publish_any_files(review_case, tmp_path):
    source, feedback = review_case
    (tmp_path / 'audio_transcript.json').write_bytes(source)
    feedback['source']['transcript_sha256'] = '0' * 64
    path = tmp_path / 'feedback.json'; path.write_text(json.dumps(feedback))
    with pytest.raises(ValueError, match='matching transcript fingerprint'):
        import_feedback(tmp_path, path, 'meeting.mp4')
    assert not (tmp_path / 'audio_transcript.reviewed.json').exists()
    assert not (tmp_path / 'audio_subtitles.reviewed.srt').exists()


def test_feedback_pipeline_reanalyzes_named_subtitles_without_running_asr(review_case, tmp_path, monkeypatch):
    from src.main import process_video
    source, feedback = review_case
    (tmp_path / 'audio_transcript.json').write_bytes(source)
    (tmp_path / 'audio_subtitles.srt').write_text('Original subtitles')
    (tmp_path / 'meeting_analysis.json').write_text('[]')
    media = tmp_path / 'meeting.mp4'; media.touch()
    feedback_path = tmp_path / 'feedback.json'; feedback_path.write_text(json.dumps(feedback))
    monkeypatch.setattr('src.main.create_transcriber', lambda *a, **k: pytest.fail('ASR must not run'))
    class Extractor:
        def __init__(self, subtitle_path, **kwargs):
            content = Path(subtitle_path).read_text()
            assert '[Reviewer Two]' in content and 'Data Record button' in content

        def extract_key_moments(self):
            return []
    monkeypatch.setattr('src.main.KeyMomentsExtractor', Extractor)
    process_video(str(media), str(tmp_path), skip_to='analyze', api_provider='apple',
                  feedback_path=str(feedback_path))
    assert (tmp_path / 'meeting_reviewed_summary.html').exists()
    assert (tmp_path / 'meeting_analysis.reviewed.json').exists()
    assert (tmp_path / 'audio_transcript.json').read_bytes() == source
    assert (tmp_path / 'audio_subtitles.srt').read_text() == 'Original subtitles'
