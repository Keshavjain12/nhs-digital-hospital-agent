"""Settings tests that need no database."""

from __future__ import annotations

import pytest

from app.core.config import Settings

SECRET = "a-test-signing-key-that-is-long-enough-to-pass"


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@db.example:5432/hospital", "postgresql://u:p@db.example:5432/hospital"],
)
def test_a_platform_database_url_gets_the_async_driver(given: str) -> None:
    """Render hands out plain URLs; the API must not fall back to an uninstalled driver."""
    settings = Settings(database_url=given, jwt_secret=SECRET)  # type: ignore[arg-type]

    assert str(settings.database_url) == "postgresql+asyncpg://u:p@db.example:5432/hospital"


def test_an_explicit_driver_is_left_alone() -> None:
    url = "postgresql+asyncpg://u:p@db.example:5432/hospital"
    settings = Settings(database_url=url, jwt_secret=SECRET)  # type: ignore[arg-type]

    assert str(settings.database_url) == url
