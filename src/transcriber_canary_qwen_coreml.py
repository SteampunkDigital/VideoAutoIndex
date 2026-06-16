import json
import os
import shutil
import wave
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Protocol

import numpy as np


DEFAULT_MODEL_NAME = "phequals/canary-qwen-2.5b-coreml-fp16"
DEFAULT_EMBEDDING_MODEL_NAME = "nvidia/canary-qwen-2.5b"
DEFAULT_TOKENIZER_NAME = "Qwen/Qwen3-1.7B"
TARGET_SAMPLE_RATE = 16000
DEFAULT_COREML_CACHE_DIR = Path.home() / ".cache" / "video-auto-index" / "canary-qwen-coreml"
MEL_BINS = 128
MEL_FRAMES = 500
N_FFT = 512
WINDOW_LENGTH = 400
HOP_LENGTH = 160
HEAD_DIM = 128
ROPE_THETA = 1_000_000.0
AUDIO_PLACEHOLDER = "<|audioplaceholder|>"
ASR_PROMPT = f"Transcribe the following: {AUDIO_PLACEHOLDER}"
COREML_PACKAGES = {
    "encoder": "encoder.mlpackage",
    "projection": "projection.mlpackage",
    "decoder": "canary_decoder_stateful.mlpackage",
    "lm_head": "canary_lm_head.mlpackage",
}


class CanaryQwenBackend(Protocol):
    def transcribe_chunk(self, audio: np.ndarray, sample_rate: int) -> str:
        """Return transcript text for one mono float32 audio chunk."""


@dataclass(frozen=True)
class AudioChunk:
    audio: np.ndarray
    start: float
    end: float


class CoreMLCanaryQwenBackend:
    """CoreML backend boundary for Canary-Qwen.

    The public transcriber is intentionally independent from the heavy model
    runtime so tests can mock inference. This backend validates CoreML artifacts,
    loads the four mlpackages, and exposes their interfaces. The remaining work
    is the model-specific autoregressive decoder loop.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        model_dir: Optional[str] = None,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
        embedding_model_dir: Optional[str] = None,
        tokenizer_name: str = DEFAULT_TOKENIZER_NAME,
        max_new_tokens: int = 128,
        no_repeat_ngram_size: int = 0,
        repetition_stop_ngram_size: int = 3,
    ):
        self.model_name = model_name
        self.model_dir = model_dir
        self.embedding_model_name = embedding_model_name
        self.embedding_model_dir = embedding_model_dir
        self.tokenizer_name = tokenizer_name
        self.max_new_tokens = max_new_tokens
        self.no_repeat_ngram_size = no_repeat_ngram_size
        self.repetition_stop_ngram_size = repetition_stop_ngram_size
        self.model_path = self._resolve_model_path()
        self.models = self._load_models()
        self.model_interfaces = self._describe_models()
        self.tokenizer = self._load_tokenizer()
        self.embeddings = self._load_embeddings()
        self.audio_placeholder_token_ids = self.tokenizer(
            AUDIO_PLACEHOLDER,
            add_special_tokens=False,
        ).input_ids
        self.eos_token_ids = {
            token_id
            for token_id in [
                self.tokenizer.eos_token_id,
                self.tokenizer.convert_tokens_to_ids("<|im_end|>"),
            ]
            if token_id is not None and token_id >= 0
        }

    def _resolve_model_path(self) -> Path:
        if self.model_dir:
            model_path = Path(self.model_dir).expanduser()
            if not model_path.exists():
                raise RuntimeError(f"Canary-Qwen CoreML model directory not found: {model_path}")
            self._validate_native_dependencies()
            self._validate_coreml_artifacts(model_path)
            return self._materialize_coreml_packages(model_path)

        if self.model_name == "nvidia/canary-qwen-2.5b":
            raise RuntimeError(
                "nvidia/canary-qwen-2.5b is a PyTorch/NeMo checkpoint and cannot be "
                "run by the native Qwen transcriber. Use the CoreML artifact repo "
                f"'{DEFAULT_MODEL_NAME}' or pass model_dir pointing at an already "
                "downloaded CoreML package set."
            )
        if self.model_name != DEFAULT_MODEL_NAME:
            raise RuntimeError(
                f"Unsupported CoreML Canary-Qwen model '{self.model_name}'. "
                f"Use '{DEFAULT_MODEL_NAME}' or pass model_dir pointing at an "
                "already downloaded compatible CoreML package set."
            )

        self._validate_native_dependencies()
        try:
            from huggingface_hub import snapshot_download

            model_path = Path(
                snapshot_download(
                    repo_id=self.model_name,
                    allow_patterns=[
                        "encoder.mlpackage/**",
                        "projection.mlpackage/**",
                        "canary_decoder_stateful.mlpackage/**",
                        "canary_lm_head.mlpackage/**",
                        "README.md",
                    ],
                )
            )
            self._validate_coreml_artifacts(model_path)
            return self._materialize_coreml_packages(model_path)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to download Canary-Qwen CoreML artifacts from '{self.model_name}'. "
                "Set model_dir to a local compatible CoreML package set if offline."
            ) from exc

    def _validate_native_dependencies(self):
        try:
            import coremltools  # noqa: F401
            import huggingface_hub  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Canary-Qwen CoreML transcription requires coremltools and "
                "huggingface_hub. Install project dependencies, then retry."
            ) from exc

    def _validate_coreml_artifacts(self, model_path: Path):
        required_paths = list(COREML_PACKAGES.values())
        missing = [name for name in required_paths if not (model_path / name).exists()]
        if missing:
            raise RuntimeError(
                f"Canary-Qwen CoreML model directory is missing: {', '.join(missing)}"
            )
        missing_weights = [
            str(Path(name) / "Data" / "com.apple.CoreML" / "weights" / "weight.bin")
            for name in required_paths
            if not (model_path / name / "Data" / "com.apple.CoreML" / "weights" / "weight.bin").exists()
        ]
        if missing_weights:
            raise RuntimeError(
                f"Canary-Qwen CoreML model directory is missing weights: {', '.join(missing_weights)}"
            )

    def _materialize_coreml_packages(self, snapshot_path: Path) -> Path:
        if not self._contains_symlinks(snapshot_path):
            return snapshot_path

        cache_root = Path(
            os.environ.get("VIDEO_AUTO_INDEX_COREML_CACHE", str(DEFAULT_COREML_CACHE_DIR))
        ).expanduser()
        materialized_path = cache_root / snapshot_path.name
        if self._has_materialized_packages(materialized_path):
            return materialized_path

        os.makedirs(materialized_path, exist_ok=True)
        readme_path = snapshot_path / "README.md"
        if readme_path.exists():
            shutil.copy2(readme_path, materialized_path / "README.md", follow_symlinks=True)

        for package_name in COREML_PACKAGES.values():
            source = snapshot_path / package_name
            destination = materialized_path / package_name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination, symlinks=False)

        self._validate_coreml_artifacts(materialized_path)
        return materialized_path

    def _contains_symlinks(self, model_path: Path) -> bool:
        for package_name in COREML_PACKAGES.values():
            package_path = model_path / package_name
            if package_path.is_symlink():
                return True
            for child in package_path.rglob("*"):
                if child.is_symlink():
                    return True
        return False

    def _has_materialized_packages(self, model_path: Path) -> bool:
        try:
            self._validate_coreml_artifacts(model_path)
        except RuntimeError:
            return False
        return not self._contains_symlinks(model_path)

    def _load_models(self) -> Dict[str, object]:
        import coremltools as ct

        return {
            name: ct.models.MLModel(
                str(self.model_path / package_name),
                compute_units=ct.ComputeUnit.ALL,
            )
            for name, package_name in COREML_PACKAGES.items()
        }

    def _describe_models(self) -> Dict[str, dict]:
        return {
            name: {
                "inputs": self._describe_features(model.get_spec().description.input),
                "outputs": self._describe_features(model.get_spec().description.output),
            }
            for name, model in self.models.items()
        }

    def _describe_features(self, features) -> List[dict]:
        descriptions = []
        for feature in features:
            descriptions.append(
                {
                    "name": feature.name,
                    "type": feature.type.WhichOneof("Type"),
                    "shape": self._feature_shape(feature),
                }
            )
        return descriptions

    def _feature_shape(self, feature) -> Optional[List[int]]:
        feature_type = feature.type
        type_name = feature_type.WhichOneof("Type")
        if type_name == "multiArrayType":
            return list(feature_type.multiArrayType.shape)
        if type_name == "imageType":
            return [feature_type.imageType.height, feature_type.imageType.width]
        return None

    def _load_tokenizer(self):
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(self.tokenizer_name)

    def _load_embeddings(self) -> np.ndarray:
        try:
            from safetensors.torch import safe_open
        except ImportError as exc:
            raise RuntimeError(
                "Canary-Qwen CoreML transcription requires safetensors to load "
                "token embeddings from the base model."
            ) from exc

        embedding_path = self._resolve_embedding_path()
        with safe_open(embedding_path, framework="pt", device="cpu") as weights:
            embedding_tensor = weights.get_tensor("embed_tokens.weight").to(dtype=__import__("torch").float32)
        return embedding_tensor.numpy()

    def _resolve_embedding_path(self) -> Path:
        if self.embedding_model_dir:
            embedding_path = Path(self.embedding_model_dir).expanduser() / "model.safetensors"
            if not embedding_path.exists():
                raise RuntimeError(f"Canary-Qwen embedding weights not found: {embedding_path}")
            return embedding_path

        from huggingface_hub import snapshot_download

        model_path = Path(
            snapshot_download(
                repo_id=self.embedding_model_name,
                allow_patterns=["model.safetensors", "config.json"],
            )
        )
        embedding_path = model_path / "model.safetensors"
        if not embedding_path.exists():
            raise RuntimeError(f"Canary-Qwen embedding weights not found: {embedding_path}")
        return embedding_path

    def transcribe_chunk(self, audio: np.ndarray, sample_rate: int) -> str:
        if sample_rate != TARGET_SAMPLE_RATE:
            raise ValueError(f"Expected {TARGET_SAMPLE_RATE} Hz audio, got {sample_rate} Hz")

        audio_features = self._audio_to_log_mel(audio)
        encoder_output = self.models["encoder"].predict({"audio_signal": audio_features})[
            "encoder_output"
        ]
        projected_audio = self.models["projection"].predict({"encoder_output": encoder_output})[
            "projected_output"
        ].astype(np.float32)

        prompt_embeddings = self._build_prompt_embeddings(projected_audio)
        generated_ids = self._greedy_decode(prompt_embeddings)
        return self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

    def _build_prompt_embeddings(self, projected_audio: np.ndarray) -> np.ndarray:
        prompt_text = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": ASR_PROMPT}],
            tokenize=False,
            add_generation_prompt=True,
        )
        if AUDIO_PLACEHOLDER not in prompt_text:
            raise RuntimeError("Failed to locate audio placeholder in Qwen rendered prompt")

        before_text, after_text = prompt_text.split(AUDIO_PLACEHOLDER, 1)
        before_ids = self.tokenizer(before_text, add_special_tokens=False).input_ids
        after_ids = self.tokenizer(after_text, add_special_tokens=False).input_ids
        before_embeddings = self._embed_token_ids(before_ids)
        after_embeddings = self._embed_token_ids(after_ids)
        return np.concatenate(
            [before_embeddings, projected_audio.astype(np.float32), after_embeddings],
            axis=1,
        )

    def _embed_token_ids(self, token_ids: List[int]) -> np.ndarray:
        if not token_ids:
            return np.zeros((1, 0, self.embeddings.shape[1]), dtype=np.float32)
        return self.embeddings[np.asarray(token_ids, dtype=np.int64)][None, :, :].astype(np.float32)

    def _greedy_decode(self, prompt_embeddings: np.ndarray) -> List[int]:
        decoder = self.models["decoder"]
        state = decoder.make_state()
        sequence_length = prompt_embeddings.shape[1]
        if sequence_length > 256:
            raise RuntimeError(
                f"CoreML decoder prompt is {sequence_length} tokens, exceeding its 256-token cache"
            )

        hidden = decoder.predict(
            {
                "hidden_states": prompt_embeddings,
                "position_cos": self._position_cos(sequence_length, start=0),
                "position_sin": self._position_sin(sequence_length, start=0),
                "attention_mask": self._causal_mask(sequence_length),
            },
            state=state,
        )["output_hidden"]
        logits = self.models["lm_head"].predict({"hidden_states": hidden[:, -1:, :]})["logits"]
        generated_ids = []
        next_token_id = self._select_next_token(logits[0, -1], generated_ids)

        while len(generated_ids) < self.max_new_tokens and next_token_id not in self.eos_token_ids:
            generated_ids.append(next_token_id)
            if self._has_repeated_tail_ngram(generated_ids):
                del generated_ids[-self.repetition_stop_ngram_size :]
                break
            current_position = sequence_length + len(generated_ids) - 1
            if current_position >= 256:
                break
            token_embedding = self._embed_token_ids([next_token_id])
            hidden = decoder.predict(
                {
                    "hidden_states": token_embedding,
                    "position_cos": self._position_cos(1, start=current_position),
                    "position_sin": self._position_sin(1, start=current_position),
                    "attention_mask": np.zeros(
                        (1, 1, 1, current_position + 1),
                        dtype=np.float32,
                    ),
                },
                state=state,
            )["output_hidden"]
            logits = self.models["lm_head"].predict({"hidden_states": hidden[:, -1:, :]})["logits"]
            next_token_id = self._select_next_token(logits[0, -1], generated_ids)
        return generated_ids

    def _select_next_token(self, logits: np.ndarray, generated_ids: List[int]) -> int:
        filtered = logits.copy()
        for token_id in self._repeated_ngram_bans(generated_ids):
            if 0 <= token_id < filtered.shape[0]:
                filtered[token_id] = -np.inf
        return int(np.argmax(filtered))

    def _repeated_ngram_bans(self, generated_ids: List[int]) -> set[int]:
        ngram_size = self.no_repeat_ngram_size
        if ngram_size <= 0 or len(generated_ids) < ngram_size - 1:
            return set()

        prefix = tuple(generated_ids[-(ngram_size - 1) :])
        banned = set()
        for index in range(0, len(generated_ids) - ngram_size + 1):
            ngram = tuple(generated_ids[index : index + ngram_size])
            if ngram[:-1] == prefix:
                banned.add(ngram[-1])
        return banned

    def _has_repeated_tail_ngram(self, generated_ids: List[int]) -> bool:
        ngram_size = self.repetition_stop_ngram_size
        if ngram_size <= 0 or len(generated_ids) < ngram_size * 2:
            return False
        tail = generated_ids[-ngram_size:]
        previous = generated_ids[-(ngram_size * 2) : -ngram_size]
        return tail == previous

    def _position_cos(self, length: int, start: int = 0) -> np.ndarray:
        angles = self._rope_angles(length, start)
        return np.cos(angles)[None, :, :].astype(np.float32)

    def _position_sin(self, length: int, start: int = 0) -> np.ndarray:
        angles = self._rope_angles(length, start)
        return np.sin(angles)[None, :, :].astype(np.float32)

    def _rope_angles(self, length: int, start: int = 0) -> np.ndarray:
        positions = np.arange(start, start + length, dtype=np.float32)[:, None]
        dims = np.arange(0, HEAD_DIM, 2, dtype=np.float32)
        inv_freq = 1.0 / (ROPE_THETA ** (dims / HEAD_DIM))
        half = positions * inv_freq[None, :]
        return np.repeat(half, 2, axis=1)

    def _causal_mask(self, length: int) -> np.ndarray:
        mask = np.triu(np.full((length, length), -1.0e9, dtype=np.float32), k=1)
        return mask[None, None, :, :]

    def _audio_to_log_mel(self, audio: np.ndarray) -> np.ndarray:
        padded_length = (MEL_FRAMES - 1) * HOP_LENGTH + N_FFT
        if len(audio) < padded_length:
            audio = np.pad(audio, (0, padded_length - len(audio)))
        else:
            audio = audio[:padded_length]

        frames = np.lib.stride_tricks.sliding_window_view(audio, N_FFT)[::HOP_LENGTH]
        frames = frames[:MEL_FRAMES]
        if len(frames) < MEL_FRAMES:
            frames = np.pad(frames, ((0, MEL_FRAMES - len(frames)), (0, 0)))

        window = np.hanning(WINDOW_LENGTH).astype(np.float32)
        framed = np.zeros((MEL_FRAMES, N_FFT), dtype=np.float32)
        framed[:, :WINDOW_LENGTH] = frames[:, :WINDOW_LENGTH] * window[None, :]
        spectrum = np.fft.rfft(framed, n=N_FFT, axis=1)
        power = (spectrum.real**2 + spectrum.imag**2).astype(np.float32)
        mel = self._mel_filterbank() @ power.T
        log_mel = np.log(np.maximum(mel, 1.0e-10)).astype(np.float32)
        mean = log_mel.mean(axis=1, keepdims=True)
        std = log_mel.std(axis=1, keepdims=True)
        normalized = (log_mel - mean) / np.maximum(std, 1.0e-5)
        return normalized[None, :, :].astype(np.float16)

    def _mel_filterbank(self) -> np.ndarray:
        low_mel = self._hz_to_mel(0.0)
        high_mel = self._hz_to_mel(TARGET_SAMPLE_RATE / 2)
        mel_points = np.linspace(low_mel, high_mel, MEL_BINS + 2)
        hz_points = self._mel_to_hz(mel_points)
        bins = np.floor((N_FFT + 1) * hz_points / TARGET_SAMPLE_RATE).astype(int)
        filters = np.zeros((MEL_BINS, N_FFT // 2 + 1), dtype=np.float32)
        for i in range(1, MEL_BINS + 1):
            left, center, right = bins[i - 1], bins[i], bins[i + 1]
            if center > left:
                filters[i - 1, left:center] = (np.arange(left, center) - left) / (center - left)
            if right > center:
                filters[i - 1, center:right] = (right - np.arange(center, right)) / (right - center)
        return filters

    def _hz_to_mel(self, hz):
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def _mel_to_hz(self, mel):
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)



class CanaryQwenCoreMLTranscriber:
    def __init__(
        self,
        audio_path: str,
        model_name: str = DEFAULT_MODEL_NAME,
        model_dir: Optional[str] = None,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
        embedding_model_dir: Optional[str] = None,
        tokenizer_name: str = DEFAULT_TOKENIZER_NAME,
        chunk_seconds: float = 5.0,
        overlap_seconds: float = 0.25,
        max_new_tokens: int = 32,
        no_repeat_ngram_size: int = 0,
        repetition_stop_ngram_size: int = 3,
        backend_factory: Optional[Callable[[], CanaryQwenBackend]] = None,
    ):
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be greater than 0")
        if overlap_seconds < 0:
            raise ValueError("overlap_seconds must be 0 or greater")
        if overlap_seconds >= chunk_seconds:
            raise ValueError("overlap_seconds must be smaller than chunk_seconds")

        self.audio_path = audio_path
        self.model_name = model_name
        self.model_dir = model_dir
        self.embedding_model_name = embedding_model_name
        self.embedding_model_dir = embedding_model_dir
        self.tokenizer_name = tokenizer_name
        self.chunk_seconds = chunk_seconds
        self.overlap_seconds = overlap_seconds
        self.max_new_tokens = max_new_tokens
        self.no_repeat_ngram_size = no_repeat_ngram_size
        self.repetition_stop_ngram_size = repetition_stop_ngram_size
        self._backend_factory = backend_factory

    def transcribe(self, transcript_path: str, subtitle_path: str):
        self._ensure_parent_dir(transcript_path)
        self._ensure_parent_dir(subtitle_path)

        audio, sample_rate = self._load_audio()
        chunks = []
        text_parts = []
        backend = self._create_backend()

        for audio_chunk in self._iter_chunks(audio, sample_rate):
            text = backend.transcribe_chunk(audio_chunk.audio, sample_rate).strip()
            if not text:
                continue
            if text_parts and text == text_parts[-1]:
                continue
            chunks.append(
                {
                    "timestamp": [round(audio_chunk.start, 3), round(audio_chunk.end, 3)],
                    "text": text,
                }
            )
            text_parts.append(text)

        transcript = {
            "speakers": [],
            "chunks": chunks,
            "text": " ".join(text_parts).strip(),
        }

        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript, f, indent=2, ensure_ascii=False)

        self._write_srt(transcript, subtitle_path)

    def _create_backend(self) -> CanaryQwenBackend:
        if self._backend_factory is not None:
            return self._backend_factory()
        return CoreMLCanaryQwenBackend(
            model_name=self.model_name,
            model_dir=self.model_dir,
            embedding_model_name=self.embedding_model_name,
            embedding_model_dir=self.embedding_model_dir,
            tokenizer_name=self.tokenizer_name,
            max_new_tokens=self.max_new_tokens,
            no_repeat_ngram_size=self.no_repeat_ngram_size,
            repetition_stop_ngram_size=self.repetition_stop_ngram_size,
        )

    def _load_audio(self) -> tuple[np.ndarray, int]:
        try:
            with wave.open(self.audio_path, "rb") as wav:
                if wav.getcomptype() != "NONE":
                    raise ValueError(f"Unsupported compressed WAV type: {wav.getcomptype()}")
                channels = wav.getnchannels()
                sample_rate = wav.getframerate()
                sample_width = wav.getsampwidth()
                frames = wav.readframes(wav.getnframes())
        except wave.Error as exc:
            raise ValueError(f"Invalid or unsupported WAV audio: {self.audio_path}") from exc

        audio = self._decode_pcm(frames, sample_width, channels)
        if sample_rate != TARGET_SAMPLE_RATE:
            audio = self._resample_linear(audio, sample_rate, TARGET_SAMPLE_RATE)
            sample_rate = TARGET_SAMPLE_RATE
        return audio.astype(np.float32, copy=False), sample_rate

    def _decode_pcm(self, frames: bytes, sample_width: int, channels: int) -> np.ndarray:
        if sample_width == 1:
            audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sample_width == 2:
            audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        elif sample_width == 3:
            raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
            signed = (
                raw[:, 0].astype(np.int32)
                | (raw[:, 1].astype(np.int32) << 8)
                | (raw[:, 2].astype(np.int32) << 16)
            )
            signed = np.where(signed & 0x800000, signed | ~0xFFFFFF, signed)
            audio = signed.astype(np.float32) / 8388608.0
        elif sample_width == 4:
            audio = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        return np.clip(audio, -1.0, 1.0)

    def _iter_chunks(self, audio: np.ndarray, sample_rate: int) -> Iterable[AudioChunk]:
        total_samples = len(audio)
        if total_samples == 0:
            return

        chunk_samples = int(round(self.chunk_seconds * sample_rate))
        overlap_samples = int(round(self.overlap_seconds * sample_rate))
        step_samples = max(1, chunk_samples - overlap_samples)

        start = 0
        while start < total_samples:
            end = min(total_samples, start + chunk_samples)
            yield AudioChunk(
                audio=audio[start:end],
                start=start / sample_rate,
                end=end / sample_rate,
            )
            if end == total_samples:
                break
            start += step_samples

    def _resample_linear(
        self,
        audio: np.ndarray,
        source_rate: int,
        target_rate: int,
    ) -> np.ndarray:
        if len(audio) == 0:
            return audio.astype(np.float32)

        duration = len(audio) / source_rate
        target_length = max(1, int(round(duration * target_rate)))
        source_positions = np.linspace(0.0, duration, num=len(audio), endpoint=False)
        target_positions = np.linspace(0.0, duration, num=target_length, endpoint=False)
        return np.interp(target_positions, source_positions, audio).astype(np.float32)

    def _write_srt(self, transcript: dict, srt_path: str):
        with open(srt_path, "w", encoding="utf-8") as f:
            for index, chunk in enumerate(transcript["chunks"], 1):
                start, end = chunk["timestamp"]
                f.write(f"{index}\n")
                f.write(f"{self._format_timestamp(start)} --> {self._format_timestamp(end)}\n")
                f.write(f"{chunk['text'].strip()}\n\n")

    def _format_timestamp(self, seconds: float) -> str:
        td = timedelta(seconds=max(0.0, seconds or 0.0))
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        seconds = td.seconds % 60
        milliseconds = round(td.microseconds / 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _ensure_parent_dir(self, path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)


# Backward-compatible aliases for the initial experimental module name.
MLXCanaryQwenBackend = CoreMLCanaryQwenBackend
CanaryQwenMLXTranscriber = CanaryQwenCoreMLTranscriber
