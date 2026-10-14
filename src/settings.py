"""Central place for reading configuration.

Order of precedence: environment variable -> Streamlit secrets -> default.
Nothing in this module ever logs or returns a value to the UI.
"""
from __future__ import annotations

import os
from typing import Optional

import streamlit as st


def get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value:
        return value
    try:
        secret = st.secrets.get(name)  # raises if no secrets file exists
    except Exception:
        secret = None
    return str(secret) if secret else default


# Tunable recognition thresholds (documented in README).
FACE_MATCH_THRESHOLD = float(get_setting("FACE_MATCH_THRESHOLD", "0.45"))
VOICE_MATCH_THRESHOLD = float(get_setting("VOICE_MATCH_THRESHOLD", "0.65"))
# Ambiguity margin: if the 2nd-best candidate is also within the threshold and closer than
# this to the best, the face is sent to teacher review instead of auto-assigned.
# PROVISIONAL default: not yet tuned on real labelled data (see evaluation/README).
FACE_MATCH_MARGIN = float(get_setting("FACE_MATCH_MARGIN", "0.05"))
# dlib re-sampling jitter for embeddings (0 = fastest; higher = slightly more stable, slower).
FACE_NUM_JITTERS = int(get_setting("FACE_NUM_JITTERS", "0"))
# Faces whose bounding box is smaller than this (pixels) are flagged as low quality.
FACE_MIN_SIZE_PX = int(get_setting("FACE_MIN_SIZE_PX", "40"))
# Voice: 2nd-best speaker within this similarity of the best (and above threshold) => teacher review.
# PROVISIONAL, not tuned on labelled recordings.
VOICE_MATCH_MARGIN = float(get_setting("VOICE_MATCH_MARGIN", "0.05"))
