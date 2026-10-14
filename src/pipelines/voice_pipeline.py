"""Voice identification pipeline (Resemblyzer speaker embeddings + cosine similarity).

Heavy ML imports are lazy so the rest of the app (and unit tests) work without
PyTorch installed. This module never touches Streamlit; failures raise
`VoiceError` and the UI decides how to show them.
"""
from __future__ import annotations

import io
import logging

import numpy as np
import streamlit as st

from dataclasses import dataclass, field

from src.settings import VOICE_MATCH_MARGIN, VOICE_MATCH_THRESHOLD

log = logging.getLogger("smartattend.voice")
SAMPLE_RATE = 16000
MIN_SEGMENT_SECONDS = 0.5


class VoiceError(RuntimeError):
    """Voice processing failed; message is safe to show to users."""


@st.cache_resource(show_spinner="Loading voice model…")
def load_voice_encoder():
    from resemblyzer import VoiceEncoder

    return VoiceEncoder()


def _load_audio(audio_bytes: bytes) -> np.ndarray:
    import librosa

    try:
        audio, _ = librosa.load(io.BytesIO(audio_bytes), sr=SAMPLE_RATE)
    except Exception as exc:  # noqa: BLE001
        log.exception("Could not decode audio")
        raise VoiceError("Could not read the audio recording. Please record again.") from exc
    if audio.size == 0:
        raise VoiceError("The recording is empty.")
    return audio


def get_voice_embedding(audio_bytes: bytes) -> list[float]:
    from resemblyzer import preprocess_wav

    audio = _load_audio(audio_bytes)
    try:
        wav = preprocess_wav(audio)
        return load_voice_encoder().embed_utterance(wav).tolist()
    except Exception as exc:  # noqa: BLE001
        log.exception("Voice embedding failed")
        raise VoiceError("Could not analyse the voice recording. Try a longer, clearer sample.") from exc


def cosine_similarity(a, b) -> float:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return 0.0 if denom == 0 else float(np.dot(a, b) / denom)


# ------------------------------------------------------------------ audio quality
MIN_SECONDS, MAX_SECONDS = 1.0, 600.0


@dataclass
class AudioQuality:
    duration: float
    peak: float
    clipped_fraction: float
    speech_fraction: float
    snr_db: float
    issues: list[str] = field(default_factory=list)
    fatal: bool = False


def assess_audio(audio: np.ndarray, sr: int = SAMPLE_RATE) -> AudioQuality:
    """Cheap, explainable checks on a mono float waveform in [-1, 1]. No ML involved."""
    audio = np.asarray(audio, dtype=np.float64).ravel()
    dur = len(audio) / sr if sr else 0.0
    q = AudioQuality(dur, float(np.max(np.abs(audio))) if audio.size else 0.0, 0.0, 0.0, 0.0)
    if audio.size == 0 or not np.isfinite(audio).all():
        q.issues.append("The recording is empty or corrupt."); q.fatal = True
        return q
    if dur < MIN_SECONDS:
        q.issues.append(f"Recording is too short ({dur:.1f}s). Record at least {MIN_SECONDS:.0f}s."); q.fatal = True
    if dur > MAX_SECONDS:
        q.issues.append("Recording is too long (max 10 minutes)."); q.fatal = True
    if q.peak < 0.01:
        q.issues.append("The recording is silent: check the microphone and its permissions."); q.fatal = True
        return q
    q.clipped_fraction = float(np.mean(np.abs(audio) >= 0.99))
    if q.clipped_fraction > 0.01:
        q.issues.append("Audio is clipped (too loud). Move back from the microphone.")
    frame = int(0.03 * sr)
    n = len(audio) // frame
    if n >= 5:
        rms = np.sqrt(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1)) + 1e-9
        db = 20 * np.log10(rms)
        q.speech_fraction = float(np.mean(db > db.max() - 30))
        q.snr_db = float(np.percentile(db, 90) - np.percentile(db, 10))
        if q.speech_fraction < 0.05:
            q.issues.append("Almost no speech detected."); q.fatal = True
        if q.snr_db < 10:
            q.issues.append("Background noise is high relative to speech; results may be unreliable.")
    return q


# ------------------------------------------------------------------ matching
@dataclass
class SpeakerMatch:
    status: str                      # matched | ambiguous | unknown
    student_id: int | None = None
    score: float = 0.0
    second_score: float | None = None
    candidates: list[int] = field(default_factory=list)


def rank_speakers(embedding, candidates: dict[int, list[float]], threshold: float = VOICE_MATCH_THRESHOLD,
                  margin: float = VOICE_MATCH_MARGIN) -> SpeakerMatch:
    """Never returns the nearest speaker blindly: weak => unknown, too close to call => ambiguous."""
    if embedding is None or not candidates:
        return SpeakerMatch("unknown")
    scored = sorted(((cosine_similarity(embedding, e), sid) for sid, e in candidates.items() if e), reverse=True)
    if not scored:
        return SpeakerMatch("unknown")
    best, sid = scored[0]
    second = scored[1][0] if len(scored) > 1 else None
    if best < threshold:
        return SpeakerMatch("unknown", None, max(best, 0.0), second)
    close = [s for sc, s in scored if sc >= threshold and best - sc < margin]
    if len(close) > 1:
        return SpeakerMatch("ambiguous", None, best, second, close)
    return SpeakerMatch("matched", sid, best, second, [sid])


def identify_speaker(new_embedding, candidates_dict: dict[int, list[float]], threshold: float = VOICE_MATCH_THRESHOLD):
    """Back-compatible helper: (student_id | None, best_score). Ambiguous counts as None."""
    m = rank_speakers(new_embedding, candidates_dict, threshold)
    return m.student_id, m.score


@dataclass
class BulkVoiceResult:
    matched: dict[int, float] = field(default_factory=dict)
    ambiguous: list[list[int]] = field(default_factory=list)  # candidate groups needing review
    segments: int = 0
    quality: AudioQuality | None = None


def process_bulk_audio_detailed(audio_bytes: bytes, candidates: dict[int, list[float]],
                                threshold: float = VOICE_MATCH_THRESHOLD, margin: float = VOICE_MATCH_MARGIN) -> BulkVoiceResult:
    """Split a classroom recording on silence and identify each speaker segment."""
    import librosa
    from resemblyzer import preprocess_wav

    audio = _load_audio(audio_bytes)
    quality = assess_audio(audio)
    if quality.fatal:
        raise VoiceError(" ".join(quality.issues))
    encoder = load_voice_encoder()
    out = BulkVoiceResult(quality=quality)
    for start, end in librosa.effects.split(audio, top_db=30):
        if (end - start) < SAMPLE_RATE * MIN_SEGMENT_SECONDS:
            continue
        try:
            embedding = encoder.embed_utterance(preprocess_wav(audio[start:end]))
        except Exception:  # noqa: BLE001 - skip a bad segment, keep the rest
            log.warning("Skipping an unreadable audio segment", exc_info=True)
            continue
        out.segments += 1
        m = rank_speakers(embedding, candidates, threshold, margin)
        if m.status == "matched" and m.score > out.matched.get(m.student_id, -1.0):
            out.matched[m.student_id] = m.score
        elif m.status == "ambiguous":
            out.ambiguous.append(m.candidates)
    return out


def process_bulk_audio(audio_bytes: bytes, candidates: dict[int, list[float]], threshold: float = VOICE_MATCH_THRESHOLD) -> dict[int, float]:
    return process_bulk_audio_detailed(audio_bytes, candidates, threshold).matched
