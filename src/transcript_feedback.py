"""Validate page feedback and apply confirmed edits to an existing transcript."""

import hashlib
import json
import math
import re
from pathlib import Path

from .transcript import normalize_chunk, write_transcript

FEEDBACK_TYPE = 'video-auto-index.transcript-feedback'


def validate_feedback(feedback):
    if not isinstance(feedback, dict) or type(feedback.get('schema_version')) is not int or feedback['schema_version'] != 1:
        raise ValueError('Unsupported transcript feedback schema_version (expected 1)')
    if feedback.get('type') != FEEDBACK_TYPE:
        raise ValueError('Not a video-auto-index transcript feedback file')
    source = feedback.get('source')
    if not isinstance(source, dict) or not isinstance(source.get('transcript_sha256'), str) or not re.fullmatch(
        r'[0-9a-f]{64}', source['transcript_sha256']
    ):
        raise ValueError('Feedback requires the source transcript SHA-256')
    if not isinstance(feedback.get('speakers'), list) or not isinstance(feedback.get('regions'), list):
        raise ValueError('Feedback requires speakers and regions arrays')


def apply_feedback(source_bytes, feedback, media_file):
    """Apply exact user edits; word hints are retained, never sent as a global ASR prompt."""
    validate_feedback(feedback)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source_hash != feedback['source']['transcript_sha256']:
        raise ValueError('Feedback fingerprint does not match this transcript')
    if feedback['source'].get('media_file') != media_file:
        raise ValueError('Feedback media_file does not match the selected recording')
    data = json.loads(source_bytes)
    chunks = [normalize_chunk(chunk, index) for index, chunk in enumerate(data['chunks'])]
    by_id = {chunk['id']: chunk for chunk in chunks}
    if len(by_id) != len(chunks):
        raise ValueError('Transcript has duplicate segment IDs; feedback would be ambiguous')
    speaker_ids = {c['speaker'] for c in chunks if c.get('speaker')}
    speaker_ids.update(s for s in data.get('speakers', []) if isinstance(s, str))
    names = dict(data.get('speaker_names', {}))
    seen_speakers = set()
    for speaker in feedback['speakers']:
        if not isinstance(speaker, dict):
            raise ValueError('Invalid speaker mapping')
        speaker_id, name = speaker.get('speaker_id'), speaker.get('name')
        if not isinstance(speaker_id, str) or speaker_id not in speaker_ids or speaker_id in seen_speakers:
            raise ValueError(f'Unknown or duplicate speaker ID: {speaker_id}')
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError('Speaker names must contain 1 to 120 characters')
        names[speaker_id] = ' '.join(name.split())
        seen_speakers.add(speaker_id)

    seen_regions = set()
    for region in feedback['regions']:
        if not isinstance(region, dict) or not isinstance(region.get('segment_id'), str):
            raise ValueError('Invalid feedback region')
        segment_id = region['segment_id']
        if segment_id not in by_id or segment_id in seen_regions:
            raise ValueError(f'Unknown or duplicate region: {segment_id}')
        chunk = by_id[segment_id]
        times = [region.get('start_seconds'), region.get('end_seconds')]
        if any(isinstance(t, bool) or not isinstance(t, (float, int)) or not math.isfinite(t) for t in times):
            raise ValueError(f'Invalid region timestamps: {segment_id}')
        if any(abs(actual - expected) > 1e-6 for actual, expected in zip(times, chunk['timestamp'])):
            raise ValueError(f'Region timestamps changed: {segment_id}')
        if region.get('original_text') != chunk['text']:
            raise ValueError(f'Original text changed: {segment_id}')
        if region.get('speaker_id') != chunk.get('speaker'):
            raise ValueError(f'Region speaker ID changed: {segment_id}')
        expected_name = names.get(chunk.get('speaker'), chunk.get('speaker'))
        if region.get('speaker_name') != expected_name:
            raise ValueError(f'Region speaker name does not match speaker mapping: {segment_id}')
        if not isinstance(region.get('corrected_text'), str):
            raise ValueError(f'Region requires corrected_text: {segment_id}')
        hints = region.get('word_hints', [])
        if not isinstance(hints, list) or any(not isinstance(hint, dict) or
                not isinstance(hint.get('original'), str) or not isinstance(hint.get('replacement'), str)
                for hint in hints):
            raise ValueError(f'Invalid word hints: {segment_id}')
        chunk['text'] = ' '.join(region['corrected_text'].split())
        seen_regions.add(segment_id)

    # An empty correction explicitly removes the phrase; its source remains in the original file.
    data['chunks'] = [chunk for chunk in chunks if chunk['text']]
    data['text'] = ' '.join(chunk['text'] for chunk in data['chunks'])
    data['speaker_names'] = names
    data.setdefault('metadata', {})['review'] = {
        'source_transcript_sha256': source_hash,
        'feedback_sha256': hashlib.sha256(json.dumps(feedback, sort_keys=True).encode()).hexdigest(),
        'corrected_regions': feedback['regions'],
    }
    return data


def import_feedback(output_dir, feedback_path, media_file):
    """Write separate reviewed artifacts from the exact original or reviewed source."""
    folder = Path(output_dir)
    feedback = json.loads(Path(feedback_path).read_text(encoding='utf-8'))
    validate_feedback(feedback)
    source_bytes = None
    for name in ('audio_transcript.json', 'audio_transcript.reviewed.json'):
        path = folder / name
        if path.is_file():
            candidate = path.read_bytes()
            if hashlib.sha256(candidate).hexdigest() == feedback['source']['transcript_sha256']:
                source_bytes = candidate
                break
    if source_bytes is None:
        raise ValueError('No matching transcript fingerprint in --output-dir. Use the output directory for the page you edited.')
    data = apply_feedback(source_bytes, feedback, media_file)
    transcript_path, subtitle_path = folder / 'audio_transcript.reviewed.json', folder / 'audio_subtitles.reviewed.srt'
    write_transcript(data, transcript_path, subtitle_path)
    return str(transcript_path), str(subtitle_path)
