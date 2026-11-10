"""Saving and loading the queue as a JSON file under the user's config dir.

The file lives at $XDG_CONFIG_HOME/termyt/queue.json, i.e. normally
~/.config/termyt/queue.json — the standard spot for "app-local state" on
Linux/Freedesktop systems, so we never write stray files into the repo or
home directory root.

Rules, kept deliberately simple for v0.2:
- Save the whole session (queue + which track + volume) on clean quit.
- Load it at startup; a missing or broken file is NOT an error — it just
  means "nothing saved yet" / "corrupt, start fresh". A music player
  starting with an empty queue is never a fatal situation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def state_dir() -> Path:
    """Where termyt keeps its local files (created on demand)."""
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = base / "termyt"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path() -> Path:
    return state_dir() / "queue.json"


def save(
    queue: list[dict],
    *,
    index: int = -1,
    volume: int = 100,
    path: Path | None = None,
) -> int:
    """Persist queue + cursor + volume atomically. Returns count saved."""
    entries = [_clean(e) for e in queue if _clean(e)]
    data = {"index": index, "volume": volume, "entries": entries}
    target = path or state_path()
    # Write to a temp file next to the target, then rename over it.
    # The rename is atomic, so a crash mid-write can never leave a
    # half-written queue.json behind (the old file survives).
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return len(entries)


def load(path: Path | None = None) -> dict:
    """Load saved state; always returns a usable dict (possibly empty)."""
    target = path or state_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"index": -1, "volume": 100, "entries": []}
    entries = [e for e in data.get("entries", []) if _clean(e)]
    return {
        "index": data.get("index", -1),
        "volume": data.get("volume", 100),
        "entries": entries,
    }


def _clean(entry: dict) -> dict | None:
    """Keep only known keys with expected types — so a hand-edited or
    half-corrupt file can't sneak a surprise into the player. Anything
    with the wrong shape is dropped, not coerced into shape."""
    try:
        if not (
            isinstance(entry["title"], str)
            and isinstance(entry["url"], str)
            and isinstance(entry["id"], str)
        ):
            return None
        cleaned = {
            "title": entry["title"],
            "url": entry["url"],
            "id": entry["id"],
            "duration": int(entry["duration"] or 0),
        }
    except (KeyError, TypeError, ValueError):
        return None
    return cleaned if cleaned["url"] else None
