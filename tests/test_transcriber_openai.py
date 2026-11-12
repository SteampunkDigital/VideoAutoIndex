import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.transcriber_openai import OpenAITranscriber, DEFAULT_TRANSCRIPTION_MODEL
from src.transcript import format_timestamp, write_transcript


@pytest.fixture
def backend(tmp_path, monkeypatch):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"test audio")
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr("src.transcriber_openai.OpenAI", factory)
    transcriber = OpenAITranscriber(source, api_key="transcription-key", language="ja")
    factory.assert_called_once_with(api_key="transcription-key", max_retries=2, timeout=600.0)
    monkeypatch.setattr(transcriber, "_prepare_uploads", lambda directory: [(source, 0, 20)])
    return transcriber, client, source


def response(segments, text=""):
    return SimpleNamespace(model_dump=lambda: {"segments": segments, "text": text})


def test_diarization_preserves_overlaps_and_speakers(backend, tmp_path):
    transcriber, client, _ = backend
    client.audio.transcriptions.create.return_value = response([
        {"start": 12, "end": 16, "text": "はい", "speaker": "B"},
        {"start": 10, "end": 14, "text": "質問です", "speaker": "A"},
        {"start": 16, "end": 18, "text": "不明", "speaker": None},
    ])
    transcript, srt = tmp_path / "nested/transcript.json", tmp_path / "nested/subtitles.srt"
    transcriber.transcribe(transcript, srt)
    data = json.loads(transcript.read_text())
    assert [c["timestamp"] for c in data["chunks"]] == [[10, 14], [12, 16], [16, 18]]
    assert data["speakers"] == ["A", "B"]
    assert data["metadata"]["model"] == DEFAULT_TRANSCRIPTION_MODEL
    assert data["text"] == "質問です はい 不明"
    assert "00:00:10,000 --> 00:00:14,000\n[A] 質問です" in srt.read_text()
    assert "[Unknown speaker] 不明" in srt.read_text()
    kwargs = client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["model"] == DEFAULT_TRANSCRIPTION_MODEL
    assert kwargs["language"] == "ja"
    assert kwargs["response_format"] == "diarized_json"
    assert kwargs["chunking_strategy"] == "auto"
    assert "prompt" not in kwargs and "timestamp_granularities" not in kwargs


def test_multipart_offsets_and_speaker_identity(backend, tmp_path, monkeypatch):
    transcriber, client, source = backend
    monkeypatch.setattr(transcriber, "_prepare_uploads",
                        lambda directory: [(source, 0, 20), (source, 20, 20)])
    client.audio.transcriptions.create.side_effect = [
        response([{"start": 0, "end": 10, "text": "First", "speaker": "A"}]),
        response([{"start": 1, "end": 9, "text": "Second", "speaker": "A"}]),
    ]
    transcript, srt = tmp_path / "transcript.json", tmp_path / "subtitles.srt"
    transcriber.transcribe(transcript, srt)
    data = json.loads(transcript.read_text())
    assert data["chunks"][1]["timestamp"] == [21, 29]
    assert data["speakers"] == ["Part 1 / A", "Part 2 / A"]
    assert data["metadata"]["speaker_scope"] == "upload"
    assert len({c["id"] for c in data["chunks"]}) == 2


@pytest.mark.parametrize("segments", [None,
    [{"start": 2, "end": 1, "text": "bad", "speaker": "A"}],
    [{"start": float("nan"), "end": 1, "text": "bad", "speaker": "A"}],
    [{"start": 0, "end": 22, "text": "bad", "speaker": "A"}],
    [{"start": 0, "end": 1, "text": "bad", "speaker": 42}],
    [],
])
def test_invalid_response_leaves_existing_outputs(backend, tmp_path, segments):
    transcriber, client, _ = backend
    client.audio.transcriptions.create.return_value = response(segments, text="Nonempty transcript")
    transcript, srt = tmp_path / "transcript.json", tmp_path / "subtitles.srt"
    transcript.write_text("old JSON")
    srt.write_text("old SRT")
    with pytest.raises(ValueError):
        transcriber.transcribe(transcript, srt)
    assert transcript.read_text() == "old JSON"
    assert srt.read_text() == "old SRT"


def test_api_failure_does_not_publish_partial_results(backend, tmp_path, monkeypatch):
    transcriber, client, source = backend
    monkeypatch.setattr(transcriber, "_prepare_uploads",
                        lambda directory: [(source, 0, 20), (source, 20, 20)])
    client.audio.transcriptions.create.side_effect = [
        response([{"start": 0, "end": 1, "text": "First", "speaker": "A"}]),
        RuntimeError("Request failed"),
    ]
    with pytest.raises(RuntimeError, match="Request failed"):
        transcriber.transcribe(tmp_path / "transcript.json", tmp_path / "subtitles.srt")
    assert not (tmp_path / "transcript.json").exists()
    assert not (tmp_path / "subtitles.srt").exists()


def test_empty_audio_response_is_valid(backend, tmp_path):
    transcriber, client, _ = backend
    client.audio.transcriptions.create.return_value = response([])
    transcriber.transcribe(tmp_path / "transcript.json", tmp_path / "subtitles.srt")
    assert json.loads((tmp_path / "transcript.json").read_text())["chunks"] == []
    assert (tmp_path / "subtitles.srt").read_text() == ""


def test_rejects_model_without_diarization(backend):
    _, _, source = backend
    with pytest.raises(ValueError, match="separate diarization/alignment"):
        OpenAITranscriber(source, api_key="unused", model_name="gpt-transcribe")


def test_prepare_uploads_compresses_large_source(backend, tmp_path, monkeypatch):
    transcriber, _, source = backend
    monkeypatch.setattr("src.transcriber_openai.MAX_UPLOAD_BYTES", 4)
    monkeypatch.setattr(transcriber, "_duration", lambda: 42)
    monkeypatch.setattr(transcriber, "_encode", lambda target: target.write_bytes(b"mp3"))
    uploads = OpenAITranscriber._prepare_uploads(transcriber, tmp_path)
    assert uploads == [(tmp_path / "audio.mp3", 0, 42)]


def test_prepare_uploads_splits_compressed_oversize_audio(backend, tmp_path, monkeypatch):
    transcriber, _, _ = backend
    monkeypatch.setattr("src.transcriber_openai.MAX_UPLOAD_BYTES", 4)
    monkeypatch.setattr("src.transcriber_openai.SPLIT_SECONDS", 20)
    monkeypatch.setattr(transcriber, "_duration", lambda: 45.5)
    calls = []
    def encode(target, start=0, duration=None):
        calls.append((start, duration))
        target.write_bytes(b"large" if duration is None else b"mp3")
    monkeypatch.setattr(transcriber, "_encode", encode)
    uploads = OpenAITranscriber._prepare_uploads(transcriber, tmp_path)
    assert [(offset, length) for _, offset, length in uploads] == [(0, 20), (20, 20), (40, 5.5)]
    assert calls == [(0, None), (0, 20), (20, 20), (40, 5.5)]


def test_publication_failure_restores_both_outputs(tmp_path, monkeypatch):
    import os
    transcript, srt = tmp_path / "transcript.json", tmp_path / "subtitles.srt"
    transcript.write_text("old JSON")
    srt.write_text("old SRT")
    replace = os.replace
    def fail_second(source, destination):
        if destination == transcript:
            raise OSError("Cannot publish JSON")
        replace(source, destination)
    monkeypatch.setattr("src.transcript.os.replace", fail_second)
    with pytest.raises(OSError, match="Cannot publish"):
        write_transcript({"chunks": []}, transcript, srt)
    assert transcript.read_text() == "old JSON"
    assert srt.read_text() == "old SRT"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["subtitles.srt", "transcript.json"]


@pytest.mark.parametrize("seconds,expected", [(59.9999, "00:01:00,000"),
    (3599.9999, "01:00:00,000"), (0.001, "00:00:00,001")])
def test_timestamp_rounding(seconds, expected):
    assert format_timestamp(seconds) == expected


def test_real_ffmpeg_upload_compression(dummy_wav, tmp_path, monkeypatch):
    monkeypatch.setattr("src.transcriber_openai.OpenAI", Mock())
    monkeypatch.setattr("src.transcriber_openai.MAX_UPLOAD_BYTES", 6000)
    transcriber = OpenAITranscriber(dummy_wav, api_key="unused")
    uploads = transcriber._prepare_uploads(tmp_path)
    assert len(uploads) == 1
    path, offset, duration = uploads[0]
    assert path.suffix == ".mp3" and 0 < path.stat().st_size <= 6000
    assert offset == 0 and duration == pytest.approx(1, abs=0.01)


def test_sdk_multipart_request_retry_and_response_parsing(backend, tmp_path, monkeypatch):
    # Exercise the public SDK against a local HTTP stub, across SDK HTTP-client versions.
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    from openai import OpenAI
    transcriber, _, _ = backend
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            calls.append((self.path, self.headers['Content-Type'], body))
            if len(calls) == 1:
                status = 429
                payload = {"error": {"message": "Try again", "type": "rate_limit_error"}}
            else:
                status = 200
                payload = {"duration": 20, "task": "transcribe", "text": "Hello",
                    "segments": [{"type": "transcript.text.segment", "id": "seg_001", "start": 0,
                                  "end": 1, "speaker": "A", "text": "Hello"}]}
            content = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('retry-after-ms', '1')
            self.end_headers()
            self.wfile.write(content)

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        with OpenAI(api_key="fake-key", max_retries=2, timeout=5,
                    base_url=f"http://127.0.0.1:{server.server_port}/v1") as client:
            transcriber.client = client
            transcriber.transcribe(tmp_path / "transcript.json", tmp_path / "subtitles.srt")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert len(calls) == 2
    for path, content_type, body in calls:
        assert path == "/v1/audio/transcriptions"
        assert content_type.startswith("multipart/form-data;")
        for field, value in (("model", DEFAULT_TRANSCRIPTION_MODEL),
                             ("response_format", "diarized_json"),
                             ("chunking_strategy", "auto"), ("language", "ja")):
            assert f'name="{field}"\r\n\r\n{value}'.encode() in body
        assert b"test audio" in body
    assert json.loads((tmp_path / "transcript.json").read_text())["chunks"][0]["speaker"] == "A"
