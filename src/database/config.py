"""Supabase client factory.

The client is created lazily so the app can show a helpful setup screen
instead of crashing at import time when credentials are missing.

SECURITY: the key used here is a *server-side* key and must never be sent to
the browser or committed. SmartAttend uses its own username/password (teachers)
and face (students) authentication, so Row Level Security cannot identify the
end user; access control is enforced in this server-side code instead. Keep RLS
ENABLED on every table with no public policies (see supabase/schema.sql) so the
public anon key cannot read or write anything.
"""
from __future__ import annotations

import logging

import streamlit as st

from src.settings import get_setting

log = logging.getLogger("smartattend.db")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


_client_override = None  # used by tests only


def set_client_for_testing(client) -> None:
    global _client_override
    _client_override = client


@st.cache_resource(show_spinner=False)
def _create_client():
    from supabase import create_client

    url = get_setting("SUPABASE_URL")
    key = get_setting("SUPABASE_KEY")
    if not url or not key:
        raise ConfigError(
            "SUPABASE_URL and SUPABASE_KEY are not configured. "
            "Copy .env.example to .env (or .streamlit/secrets.toml.example to "
            ".streamlit/secrets.toml) and fill in your project values."
        )
    return create_client(url, key)


def get_supabase():
    if _client_override is not None:
        return _client_override
    return _create_client()
