"""Offline test: the MPRIS module imports and its helpers behave."""

import pytest

import re

from ytm.mpris import _object_path_escape


def test_path_escape_sanitizes_urls():
    escaped = _object_path_escape("https://example.com/watch?v=x&list=y")
    # must be a legal ObjectPath: leading "/", then alnum/underscore only
    assert re.fullmatch(r"/[\w/]*", escaped) is not None, escaped


def test_path_escape_truncates_long_titles():
    assert len(_object_path_escape("a" * 500)) <= 201
