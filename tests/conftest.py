import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.fake_supabase import FakeSupabase  # noqa: E402


@pytest.fixture()
def fake_db():
    from src.database import config

    fake = FakeSupabase()
    config.set_client_for_testing(fake)
    yield fake
    config.set_client_for_testing(None)
