"""Compatibility wrapper for the renamed CoreML Canary-Qwen transcriber."""

from .transcriber_canary_qwen_coreml import (
    DEFAULT_MODEL_NAME,
    TARGET_SAMPLE_RATE,
    CanaryQwenBackend,
    CanaryQwenCoreMLTranscriber,
    CoreMLCanaryQwenBackend,
)

CanaryQwenMLXTranscriber = CanaryQwenCoreMLTranscriber
MLXCanaryQwenBackend = CoreMLCanaryQwenBackend

__all__ = [
    "DEFAULT_MODEL_NAME",
    "TARGET_SAMPLE_RATE",
    "CanaryQwenBackend",
    "CanaryQwenCoreMLTranscriber",
    "CoreMLCanaryQwenBackend",
    "CanaryQwenMLXTranscriber",
    "MLXCanaryQwenBackend",
]
