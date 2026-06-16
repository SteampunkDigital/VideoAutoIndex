import json
import os
import wave

import numpy as np
import pytest

from src.transcriber_canary_qwen_coreml import (
    DEFAULT_MODEL_NAME,
    TARGET_SAMPLE_RATE,
    COREML_PACKAGES,
    CanaryQwenCoreMLTranscriber,
    CoreMLCanaryQwenBackend,
)


class FakeBackend:
    def __init__(self):
        self.calls = []

    def transcribe_chunk(self, audio, sample_rate):
        self.calls.append((audio, sample_rate))
        return f"chunk {len(self.calls)}"


@pytest.fixture
def test_audio(test_data_dir):
    return os.path.join(test_data_dir, "audio.wav")


def write_wav(path, sample_rate=TARGET_SAMPLE_RATE, duration=1.0, channels=1):
    sample_count = int(sample_rate * duration)
    samples = np.linspace(-0.25, 0.25, sample_count, dtype=np.float32)
    pcm = (samples * 32767).astype("<i2")
    if channels > 1:
        pcm = np.repeat(pcm[:, None], channels, axis=1).reshape(-1)

    with wave.open(path, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def create_fake_coreml_packages(root):
    for package_name in COREML_PACKAGES.values():
        weights_dir = os.path.join(package_name, "Data", "com.apple.CoreML", "weights")
        os.makedirs(os.path.join(root, weights_dir))
        with open(os.path.join(root, weights_dir, "weight.bin"), "wb") as f:
            f.write(b"fake weights")


def test_canary_qwen_init(test_audio):
    transcriber = CanaryQwenCoreMLTranscriber(test_audio)

    assert transcriber.audio_path == test_audio
    assert transcriber.model_name == DEFAULT_MODEL_NAME
    assert transcriber.chunk_seconds == 5.0
    assert transcriber.overlap_seconds == 0.25


def test_canary_qwen_init_invalid_path():
    with pytest.raises(FileNotFoundError):
        CanaryQwenCoreMLTranscriber("missing.wav")


def test_canary_qwen_rejects_invalid_chunk_settings(test_audio):
    with pytest.raises(ValueError, match="chunk_seconds"):
        CanaryQwenCoreMLTranscriber(test_audio, chunk_seconds=0)

    with pytest.raises(ValueError, match="overlap_seconds"):
        CanaryQwenCoreMLTranscriber(test_audio, chunk_seconds=2, overlap_seconds=2)


def test_canary_qwen_transcribe_writes_json_and_srt(temp_dir):
    audio_path = os.path.join(temp_dir, "audio.wav")
    write_wav(audio_path, duration=2.5)
    backend = FakeBackend()
    transcriber = CanaryQwenCoreMLTranscriber(
        audio_path,
        chunk_seconds=1.0,
        overlap_seconds=0.0,
        backend_factory=lambda: backend,
    )

    transcript_path = os.path.join(temp_dir, "nested", "audio_transcript.json")
    subtitle_path = os.path.join(temp_dir, "nested", "audio_subtitles.srt")
    transcriber.transcribe(transcript_path, subtitle_path)

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = json.load(f)

    assert transcript["speakers"] == []
    assert transcript["text"] == "chunk 1 chunk 2 chunk 3"
    assert [chunk["text"] for chunk in transcript["chunks"]] == ["chunk 1", "chunk 2", "chunk 3"]
    assert transcript["chunks"][0]["timestamp"] == [0.0, 1.0]
    assert transcript["chunks"][1]["timestamp"] == [1.0, 2.0]
    assert transcript["chunks"][2]["timestamp"] == [2.0, 2.5]
    assert all(sample_rate == TARGET_SAMPLE_RATE for _, sample_rate in backend.calls)

    with open(subtitle_path, "r", encoding="utf-8") as f:
        srt = f.read()

    assert "1\n00:00:00,000 --> 00:00:01,000\nchunk 1" in srt
    assert "3\n00:00:02,000 --> 00:00:02,500\nchunk 3" in srt


def test_canary_qwen_transcribe_resamples_and_mixes_to_mono(temp_dir):
    audio_path = os.path.join(temp_dir, "stereo_8k.wav")
    write_wav(audio_path, sample_rate=8000, duration=1.0, channels=2)
    backend = FakeBackend()
    transcriber = CanaryQwenCoreMLTranscriber(
        audio_path,
        backend_factory=lambda: backend,
    )

    transcript_path = os.path.join(temp_dir, "audio_transcript.json")
    subtitle_path = os.path.join(temp_dir, "audio_subtitles.srt")
    transcriber.transcribe(transcript_path, subtitle_path)

    audio, sample_rate = backend.calls[0]
    assert sample_rate == TARGET_SAMPLE_RATE
    assert audio.ndim == 1
    assert len(audio) == TARGET_SAMPLE_RATE


def test_canary_qwen_transcribe_invalid_audio(temp_dir):
    invalid_audio = os.path.join(temp_dir, "invalid.wav")
    with open(invalid_audio, "wb") as f:
        f.write(b"not a wav")

    transcriber = CanaryQwenCoreMLTranscriber(invalid_audio, backend_factory=FakeBackend)

    with pytest.raises(ValueError, match="Invalid or unsupported WAV"):
        transcriber.transcribe(
            os.path.join(temp_dir, "audio_transcript.json"),
            os.path.join(temp_dir, "audio_subtitles.srt"),
        )


def test_canary_qwen_backend_missing_model_dir(test_audio, temp_dir):
    missing_model_dir = os.path.join(temp_dir, "missing-model")

    with pytest.raises(RuntimeError, match="model directory not found"):
        CanaryQwenCoreMLTranscriber(
            test_audio,
            model_dir=missing_model_dir,
        ).transcribe(
            os.path.join(temp_dir, "audio_transcript.json"),
            os.path.join(temp_dir, "audio_subtitles.srt"),
        )


def test_canary_qwen_backend_rejects_unsupported_nvidia_checkpoint(test_audio, temp_dir):
    with pytest.raises(RuntimeError, match="PyTorch/NeMo checkpoint"):
        CanaryQwenCoreMLTranscriber(
            test_audio,
            model_name="nvidia/canary-qwen-2.5b",
        ).transcribe(
            os.path.join(temp_dir, "audio_transcript.json"),
            os.path.join(temp_dir, "audio_subtitles.srt"),
        )


def test_canary_qwen_backend_download_failure(monkeypatch, test_audio, temp_dir):
    class FakeCoreMLTools:
        pass

    class FakeHuggingFaceHub:
        @staticmethod
        def snapshot_download(**kwargs):
            raise OSError("offline")

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "coremltools":
            return FakeCoreMLTools()
        if name == "huggingface_hub":
            return FakeHuggingFaceHub()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="Failed to download Canary-Qwen CoreML artifacts"):
        CanaryQwenCoreMLTranscriber(test_audio).transcribe(
            os.path.join(temp_dir, "audio_transcript.json"),
            os.path.join(temp_dir, "audio_subtitles.srt"),
        )


def test_canary_qwen_backend_missing_dependencies(monkeypatch, temp_dir):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "coremltools":
            raise ImportError("No module named coremltools")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    create_fake_coreml_packages(temp_dir)

    with pytest.raises(RuntimeError, match="requires coremltools"):
        CoreMLCanaryQwenBackend(model_dir=temp_dir)


def test_canary_qwen_backend_loads_coreml_packages(monkeypatch, temp_dir):
    create_fake_coreml_packages(temp_dir)

    class FakeFeatureType:
        def WhichOneof(self, _):
            return "multiArrayType"

        class multiArrayType:
            shape = [1, 2, 3]

    class FakeFeature:
        def __init__(self, name):
            self.name = name
            self.type = FakeFeatureType()

    class FakeDescription:
        input = [FakeFeature("input")]
        output = [FakeFeature("output")]

    class FakeSpec:
        description = FakeDescription()

    class FakeMLModel:
        loaded_paths = []

        def __init__(self, path, compute_units=None):
            self.loaded_paths.append(path)
            self.compute_units = compute_units

        def get_spec(self):
            return FakeSpec()

    class FakeModels:
        MLModel = FakeMLModel

    class FakeCoreMLTools:
        class ComputeUnit:
            ALL = "all"

        models = FakeModels()

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "coremltools":
            return FakeCoreMLTools()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    class FakeTokenized:
        input_ids = [1, 2, 3]

    class FakeTokenizer:
        eos_token_id = 4

        def __call__(self, *args, **kwargs):
            return FakeTokenized()

        def convert_tokens_to_ids(self, _):
            return 4

    monkeypatch.setattr(CoreMLCanaryQwenBackend, "_load_tokenizer", lambda self: FakeTokenizer())
    monkeypatch.setattr(
        CoreMLCanaryQwenBackend,
        "_load_embeddings",
        lambda self: np.zeros((16, 2048), dtype=np.float32),
    )

    backend = CoreMLCanaryQwenBackend(model_dir=temp_dir)

    assert set(backend.models) == {"encoder", "projection", "decoder", "lm_head"}
    assert len(FakeMLModel.loaded_paths) == 4
    assert backend.model_interfaces["encoder"]["inputs"][0]["name"] == "input"
    assert backend.model_interfaces["encoder"]["outputs"][0]["shape"] == [1, 2, 3]


@pytest.mark.integration
def test_canary_qwen_real_model_smoke(test_audio, temp_dir):
    if os.environ.get("RUN_CANARY_QWEN_COREML") != "1":
        pytest.skip("Set RUN_CANARY_QWEN_COREML=1 to run the real Canary-Qwen CoreML smoke test")

    transcriber = CanaryQwenCoreMLTranscriber(test_audio)
    transcript_path = os.path.join(temp_dir, "audio_transcript.json")
    subtitle_path = os.path.join(temp_dir, "audio_subtitles.srt")
    transcriber.transcribe(transcript_path, subtitle_path)

    assert os.path.exists(transcript_path)
    assert os.path.exists(subtitle_path)
