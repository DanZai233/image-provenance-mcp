"""Shared fixture setup: every test works on files built in a temp dir at runtime."""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixture_builders  # noqa: E402  (path set above)

_CACHE: dict[str, str] = {}


def fixture(kind: str) -> str:
    """Return the path of a generated fixture: 'signed' or 'plain'."""
    if not _CACHE:
        tmp = tempfile.mkdtemp(prefix="image-provenance-fixtures-")
        atexit.register(shutil.rmtree, tmp, True)
        _CACHE.update(fixture_builders.write_fixtures(tmp))
    return _CACHE[kind]
