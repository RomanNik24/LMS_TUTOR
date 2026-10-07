"""Ключи сессий в Redis зависят от ``SESSION_SECRET`` (docs/09 §8)."""

from src.core.constants import SESSION_KEY_PREFIX
from src.core.session_store import _session_key


def test_session_key_depends_on_secret() -> None:
    assert _session_key("sid", "a" * 32) != _session_key("sid", "b" * 32)


def test_session_key_is_stable_and_has_prefix_and_hides_id() -> None:
    key = _session_key("sid-plain", "secret-value")
    assert key == _session_key("sid-plain", "secret-value")
    assert key.startswith(SESSION_KEY_PREFIX)
    assert "sid-plain" not in key
