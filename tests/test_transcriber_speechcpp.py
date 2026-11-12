import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.transcriber_speechcpp import (
    DEFAULT_MODELS, SpeechCppTranscriber, attribute_phrase, normalize_result,
    speech_executable, STRONG_TRANSCRIPTION_MODEL, validate_model,
)


@pytest.fixture
def raw_result():
    path = Path(__file__).resolve().parents[1] / 'test_data' / 'speechcpp_audio_result.json'
    return json.loads(path.read_text())


def test_actual_clip_retains_phrase_labels_and_overlapping_voices(raw_result):
    data = normalize_result(raw_result, DEFAULT_MODELS['en'], 'en')
    assert data['speakers'] == ['Speaker 1', 'Speaker 2']
    assert len(data['chunks']) == len(raw_result['segments']) == 16
    assert [c['speaker'] for c in data['chunks'] if c['text'] == 'Pretty convincing.'] == ['Speaker 2']
    assert [c['speaker'] for c in data['chunks'] if c['text'] == 'Convincing, yes.'] == ['Speaker 1']
    assert len({c['id'] for c in data['chunks']}) == len(data['chunks'])
    spans = data['speaker_segments']
    assert any(a['speaker'] != b['speaker'] and
               max(a['timestamp'][0], b['timestamp'][0]) < min(a['timestamp'][1], b['timestamp'][1])
               for i, a in enumerate(spans) for b in spans[i+1:])
    # Each ASR phrase appears once, even when diarization detects more than one voice.
    assert [c['text'] for c in data['chunks']] == [s['text'].strip() for s in raw_result['segments']]


def test_ambiguous_or_uncovered_phrase_is_unknown():
    timeline = [{'speaker': 'Speaker 1', 'timestamp': [0, 2]},
                {'speaker': 'Speaker 2', 'timestamp': [0, 2]}]
    assert attribute_phrase(0, 2, timeline) is None
    assert attribute_phrase(2, 3, timeline) is None
    assert attribute_phrase(0, 2, timeline[:1]) == 'Speaker 1'


def test_same_voice_is_not_double_counted_at_region_boundaries():
    payload = {'stop': 'complete', 'text': 'hello', 'segments': [
        {'start': 0, 'end': 4, 'text': 'hello'}], 'regions': [
        {'speakers': [{'speaker': 0, 'start': 0, 'end': 3}]},
        {'speakers': [{'speaker': 0, 'start': 2, 'end': 4}, {'speaker': 1, 'start': 0, 'end': 4}]}]}
    data = normalize_result(payload, DEFAULT_MODELS['en'], 'en')
    assert len(data['speaker_segments']) == 2
    assert data['chunks'][0]['speaker'] is None


@pytest.mark.parametrize('changes', [
    {'stop': 'model_limit'}, {'untimed': 'alignment failed'}, {'segments': None}, {'regions': None},
    {'segments': []},
])
def test_incomplete_or_untimed_results_are_rejected(raw_result, changes):
    with pytest.raises(ValueError):
        normalize_result({**raw_result, **changes}, DEFAULT_MODELS['en'], 'en')


def test_backend_runs_one_command_and_publishes_json_and_srt(tmp_path, monkeypatch, raw_result):
    source = tmp_path / 'meeting with spaces.wav'
    source.touch()
    monkeypatch.setattr('src.transcriber_speechcpp.speech_executable', lambda: '/path/to/speech')
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(raw_result)))
    monkeypatch.setattr('src.transcriber_speechcpp.subprocess.run', runner)
    SpeechCppTranscriber(source).transcribe(tmp_path / 'transcript.json', tmp_path / 'subtitles.srt')
    command = runner.call_args.args[0]
    assert command == ['/path/to/speech', 'asr', DEFAULT_MODELS['en'], '--timestamps',
                       '--vad', 'silero-vad', '--diarize', 'nemotron-3-diarization',
                       '--format', 'json', str(source)]
    assert '[Speaker 2] Pretty convincing.' in (tmp_path / 'subtitles.srt').read_text()
    assert json.loads((tmp_path / 'transcript.json').read_text())['speaker_segments']


def test_runtime_failure_preserves_existing_outputs(tmp_path, monkeypatch):
    source, transcript, subtitles = [tmp_path / p for p in ('audio.wav', 'transcript.json', 'subtitles.srt')]
    source.touch()
    transcript.write_text('old JSON')
    subtitles.write_text('old SRT')
    monkeypatch.setattr('src.transcriber_speechcpp.speech_executable', lambda: '/path/to/speech')
    monkeypatch.setattr('src.transcriber_speechcpp.subprocess.run', Mock(
        side_effect=subprocess.CalledProcessError(3, ['speech'])))
    with pytest.raises(subprocess.CalledProcessError):
        SpeechCppTranscriber(source).transcribe(transcript, subtitles)
    assert transcript.read_text() == 'old JSON' and subtitles.read_text() == 'old SRT'


def test_explicit_runtime_path_is_validated(tmp_path, monkeypatch):
    executable = tmp_path / 'speech'
    executable.write_text('#!/bin/sh\nexit 0\n')
    executable.chmod(0o755)
    monkeypatch.setenv('SPEECHCPP_BIN', str(executable))
    assert speech_executable() == str(executable)
    monkeypatch.setenv('SPEECHCPP_BIN', str(tmp_path / 'missing'))
    with pytest.raises(FileNotFoundError, match='not executable'):
        speech_executable()


@pytest.mark.parametrize('language', ['en', 'ja'])
def test_stronger_model_is_accepted_for_supported_languages(language):
    validate_model(STRONG_TRANSCRIPTION_MODEL, language)
    with pytest.raises(ValueError, match='phrase timing'):
        validate_model('qwen3-asr-1.7b', language)


def test_stronger_model_uses_the_same_diarization_pipeline(tmp_path, monkeypatch, raw_result):
    audio = tmp_path / 'audio.wav'
    audio.touch()
    monkeypatch.setattr('src.transcriber_speechcpp.speech_executable', lambda: '/path/to/speech')
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(raw_result)))
    monkeypatch.setattr('src.transcriber_speechcpp.subprocess.run', runner)
    SpeechCppTranscriber(audio, model_name=STRONG_TRANSCRIPTION_MODEL).transcribe(
        tmp_path / 'transcript.json', tmp_path / 'subtitles.srt')
    command = runner.call_args.args[0]
    assert command[2] == STRONG_TRANSCRIPTION_MODEL
    assert command[command.index('--diarize') + 1] == 'nemotron-3-diarization'
    assert '--timestamps' in command and '--vad' in command
    assert '--speakers' not in command  # Keep recording-wide IDs from the existing diarizer.
    data = json.loads((tmp_path / 'transcript.json').read_text())
    assert data['metadata']['model'] == STRONG_TRANSCRIPTION_MODEL
    assert data['speaker_segments']
