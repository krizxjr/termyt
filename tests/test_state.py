"""Tests for the persistence layer (src/ytm/state.py) — fully offline; a
tmp_path directory stands in for the real config dir."""

import json

from ytm import state


def _entry(i: int) -> dict:
    return {
        "title": f"Track {i}",
        "url": f"https://www.youtube.com/watch?v=dQw4w9WgXcQ{i}",
        "id": f"dQw4w9WgXcQ{i}",
        "duration": 200 + i,
    }


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "queue.json"
    queue = [_entry(0), _entry(1), _entry(2)]
    state.save(queue, index=1, volume=80, path=path)
    saved = state.load(path=path)
    assert saved["entries"] == queue
    assert saved["index"] == 1
    assert saved["volume"] == 80


def test_load_missing_file(tmp_path):
    saved = state.load(path=tmp_path / "nope.json")
    assert saved == {"index": -1, "volume": 100, "entries": []}


def test_load_corrupt_file(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text("{ this is not json ]", encoding="utf-8")
    saved = state.load(path=path)
    assert saved["entries"] == []


def test_save_filters_bad_entries(tmp_path):
    path = tmp_path / "queue.json"
    good = _entry(0)
    bad = {"title": "no url anywhere", "id": 4}
    wrong_type = {"title": 7, "url": "https://x", "id": "a", "duration": []}
    state.save([good, bad, wrong_type], path=path)
    saved = state.load(path=path)
    assert [e["title"] for e in saved["entries"]] == ["Track 0"]
    # and the file on disk must be valid JSON, safely overwriting any
    # corrupt save from a previous run
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def test_save_is_atomic(tmp_path):
    """No .json.tmp half-file is ever left behind next to the real one."""
    path = tmp_path / "queue.json"
    state.save([_entry(0)], path=path)
    assert list(tmp_path.glob("*.tmp")) == []
