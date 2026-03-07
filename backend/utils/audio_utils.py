"""
backend/utils/audio_utils.py
Audio processing utilities for STT/TTS pipeline.

Handles:
- WAV ↔ raw PCM conversion
- Audio resampling (to 16kHz for Google STT)
- Silence trimming
- Base64 encode/decode helpers
- Audio chunking for streaming STT
"""

import base64
import io
import struct
import math
from typing import Optional, Tuple
from loguru import logger


# ── WAV helpers ───────────────────────────────────────────────────────

def create_wav_header(
    sample_rate: int,
    num_channels: int,
    bits_per_sample: int,
    num_samples: int,
) -> bytes:
    """Build a standard WAV file header for raw PCM data."""
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,                # PCM subchunk size
        1,                 # AudioFormat = PCM
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header


def pcm_bytes_to_wav(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    num_channels: int = 1,
    bits_per_sample: int = 16,
) -> bytes:
    """Wrap raw PCM bytes in a WAV container."""
    num_samples = len(pcm_bytes) // (bits_per_sample // 8 * num_channels)
    header = create_wav_header(sample_rate, num_channels, bits_per_sample, num_samples)
    return header + pcm_bytes


def wav_to_pcm_bytes(wav_bytes: bytes) -> Tuple[bytes, int, int]:
    """
    Strip WAV header and return (pcm_bytes, sample_rate, num_channels).
    Handles standard 44-byte WAV headers.
    """
    if wav_bytes[:4] != b"RIFF":
        raise ValueError("Input is not a valid WAV file")

    # Parse header fields
    num_channels = struct.unpack_from("<H", wav_bytes, 22)[0]
    sample_rate = struct.unpack_from("<I", wav_bytes, 24)[0]

    # Find "data" chunk (skip past any extra chunks)
    offset = 12
    while offset < len(wav_bytes) - 8:
        chunk_id = wav_bytes[offset:offset + 4]
        chunk_size = struct.unpack_from("<I", wav_bytes, offset + 4)[0]
        if chunk_id == b"data":
            pcm_start = offset + 8
            return wav_bytes[pcm_start:pcm_start + chunk_size], sample_rate, num_channels
        offset += 8 + chunk_size

    raise ValueError("No 'data' chunk found in WAV file")


# ── Base64 helpers ────────────────────────────────────────────────────

def audio_bytes_to_base64(audio_bytes: bytes) -> str:
    """Encode audio bytes as a base64 string."""
    return base64.b64encode(audio_bytes).decode("utf-8")


def base64_to_audio_bytes(b64_string: str) -> bytes:
    """Decode a base64 audio string back to bytes."""
    # Handle data URIs like "data:audio/wav;base64,..."
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]
    return base64.b64decode(b64_string)


def pcm_base64_to_wav_base64(
    pcm_base64: str,
    sample_rate: int = 16000,
    num_channels: int = 1,
    bits_per_sample: int = 16,
) -> str:
    """Convert base64-encoded PCM to base64-encoded WAV."""
    pcm_bytes = base64_to_audio_bytes(pcm_base64)
    wav_bytes = pcm_bytes_to_wav(pcm_bytes, sample_rate, num_channels, bits_per_sample)
    return audio_bytes_to_base64(wav_bytes)


# ── Audio analysis ────────────────────────────────────────────────────

def compute_rms(pcm_bytes: bytes, bits_per_sample: int = 16) -> float:
    """Compute RMS amplitude of PCM audio (0.0 – 1.0 range)."""
    if len(pcm_bytes) < 2:
        return 0.0

    if bits_per_sample == 16:
        num_samples = len(pcm_bytes) // 2
        samples = struct.unpack(f"<{num_samples}h", pcm_bytes[:num_samples * 2])
        max_val = 32768.0
    elif bits_per_sample == 8:
        samples = struct.unpack(f"{len(pcm_bytes)}B", pcm_bytes)
        samples = [s - 128 for s in samples]  # unsigned → signed
        max_val = 128.0
    else:
        raise ValueError(f"Unsupported bits_per_sample: {bits_per_sample}")

    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return rms / max_val


def is_silent(
    pcm_bytes: bytes,
    threshold: float = 0.02,
    bits_per_sample: int = 16,
) -> bool:
    """Return True if the audio chunk is below the silence threshold."""
    return compute_rms(pcm_bytes, bits_per_sample) < threshold


def trim_silence(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    threshold: float = 0.02,
    frame_ms: int = 20,
    bits_per_sample: int = 16,
) -> bytes:
    """
    Trim leading and trailing silence from PCM audio.
    Works in frames of `frame_ms` milliseconds.
    """
    bytes_per_sample = bits_per_sample // 8
    frame_size = int(sample_rate * frame_ms / 1000) * bytes_per_sample

    frames = [
        pcm_bytes[i:i + frame_size]
        for i in range(0, len(pcm_bytes), frame_size)
        if len(pcm_bytes[i:i + frame_size]) == frame_size
    ]

    if not frames:
        return pcm_bytes

    # Find first non-silent frame
    start = 0
    for i, frame in enumerate(frames):
        if not is_silent(frame, threshold, bits_per_sample):
            start = i
            break

    # Find last non-silent frame
    end = len(frames) - 1
    for i in range(len(frames) - 1, -1, -1):
        if not is_silent(frames[i], threshold, bits_per_sample):
            end = i
            break

    trimmed = b"".join(frames[start:end + 1])
    original_duration = len(pcm_bytes) / (sample_rate * bytes_per_sample)
    trimmed_duration = len(trimmed) / (sample_rate * bytes_per_sample)
    logger.debug(
        f"Silence trimmed: {original_duration:.2f}s → {trimmed_duration:.2f}s"
    )
    return trimmed


# ── Chunking for streaming ────────────────────────────────────────────

def chunk_audio(
    pcm_bytes: bytes,
    chunk_duration_ms: int = 100,
    sample_rate: int = 16000,
    bits_per_sample: int = 16,
):
    """
    Generator that yields PCM chunks of `chunk_duration_ms` milliseconds.
    Used for streaming audio to Google STT's streaming_recognize API.
    """
    bytes_per_sample = bits_per_sample // 8
    chunk_size = int(sample_rate * chunk_duration_ms / 1000) * bytes_per_sample

    for i in range(0, len(pcm_bytes), chunk_size):
        yield pcm_bytes[i:i + chunk_size]


# ── Audio duration ────────────────────────────────────────────────────

def pcm_duration_seconds(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    bits_per_sample: int = 16,
    num_channels: int = 1,
) -> float:
    """Return duration in seconds of raw PCM audio."""
    bytes_per_sample = bits_per_sample // 8 * num_channels
    return len(pcm_bytes) / (sample_rate * bytes_per_sample)


def wav_duration_seconds(wav_bytes: bytes) -> float:
    """Return duration in seconds of a WAV file."""
    pcm, sample_rate, num_channels = wav_to_pcm_bytes(wav_bytes)
    return pcm_duration_seconds(pcm, sample_rate, 16, num_channels)
