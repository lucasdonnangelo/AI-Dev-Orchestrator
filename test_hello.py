from __future__ import annotations

import pytest

from hello import hello


def test_hello_world() -> None:
    """hello('World') should return 'Hello, World!'"""
    assert hello("World") == "Hello, World!"


def test_hello_maria() -> None:
    """hello('Maria') should return 'Hello, Maria!'"""
    assert hello("Maria") == "Hello, Maria!"


def test_hello_empty_string() -> None:
    """hello('') should return 'Hello, !' without raising errors."""
    assert hello("") == "Hello, !"
