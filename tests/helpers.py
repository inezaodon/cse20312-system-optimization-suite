"""Shared test helpers."""
from __future__ import annotations

import os

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)
