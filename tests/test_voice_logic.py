import numpy as np

from src.pipelines.voice_pipeline import assess_audio, rank_speakers

SR = 16000
rng = np.random.default_rng(2)


def speechlike(sec=3.0, amp=0.3):
    t = np.arange(int(sec * SR)) / SR
    env = (np.sin(2 * np.pi * 3 * t) > -0.2).astype(float)       # on/off bursts like syllables
    return amp * env * np.sin(2 * np.pi * 180 * t) + 0.001 * rng.normal(size=t.size)


def test_good_audio_has_no_issues():
    q = assess_audio(speechlike())
    assert not q.fatal and q.issues == [] and q.snr_db > 10 and 1.0 < q.duration < 5


def test_silent_short_empty_and_corrupt_audio_are_rejected_with_actionable_messages():
    assert assess_audio(np.zeros(SR * 3)).fatal and "silent" in assess_audio(np.zeros(SR * 3)).issues[0]
    assert "too short" in assess_audio(speechlike(0.3)).issues[0] and assess_audio(speechlike(0.3)).fatal
    assert assess_audio(np.array([])).fatal
    assert assess_audio(np.array([np.nan] * SR * 2)).fatal


def test_clipping_and_noise_are_flagged_but_not_fatal():
    clipped = np.clip(speechlike(amp=3.0), -1, 1)
    q = assess_audio(clipped)
    assert any("clipped" in i for i in q.issues) and not q.fatal
    noisy = speechlike(amp=0.02) + 0.05 * rng.normal(size=3 * SR)
    assert any("noise" in i for i in assess_audio(noisy).issues)


def unit(v):
    return v / np.linalg.norm(v)


def test_rank_speakers_matched_unknown_ambiguous():
    a, b, c = (unit(rng.normal(size=256)) for _ in range(3))
    cands = {1: a.tolist(), 2: b.tolist(), 3: c.tolist(), 4: None}
    m = rank_speakers(unit(a + 0.05 * rng.normal(size=256)), cands)
    assert (m.status, m.student_id) == ("matched", 1)
    u = rank_speakers(unit(rng.normal(size=256)), cands)
    assert u.status == "unknown" and u.student_id is None          # never the 'nearest' by default
    twin = {1: a.tolist(), 2: unit(a + 0.03 * rng.normal(size=256)).tolist()}
    amb = rank_speakers(a, twin, threshold=0.5, margin=0.1)
    assert amb.status == "ambiguous" and set(amb.candidates) == {1, 2} and amb.student_id is None
    assert rank_speakers(None, cands).status == "unknown" and rank_speakers(a, {}).status == "unknown"
