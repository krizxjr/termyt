"""YouTube search built on yt-dlp.

All yt-dlp usage lives in this one file on purpose: YouTube changes its site
regularly and yt-dlp's maintainers patch it quickly. When something here
breaks, the fix is usually just `pip install -U yt-dlp` — and at most a
change inside this file, never the rest of the app.
"""

from __future__ import annotations

from yt_dlp import YoutubeDL

# We only need metadata, so we tell yt-dlp to fetch as little as possible.
# "skip_download" never saves any audio to disk.
_SEARCH_OPTIONS = {
    "quiet": True,          # no progress bars or debug output
    "no_warnings": True,    # hide yt-dlp's warning chatter
    "skip_download": True,  # extract info only, never download media
    "extract_flat": True,   # don't resolve each video fully: much faster
}


def format_duration(seconds: int | float | None) -> str:
    """Turn a duration in seconds into a M:SS string ("3:05")."""
    total = int(seconds or 0)
    return f"{total // 60}:{total % 60:02d}"


def search(query: str, limit: int = 5) -> list[dict[str, str]]:
    """Search YouTube and return up to `limit` video info dicts.

    Each dict has "title", "url", "id", and "duration" keys. Raises
    RuntimeError if the search fails or returns nothing usable, so callers
    get one simple, descriptive exception instead of yt-dlp internals.
    """
    url = f"ytsearch{limit}:{query}"
    try:
        with YoutubeDL(_SEARCH_OPTIONS) as ydl:
            data = ydl.extract_info(url, download=False)
    except Exception as exc:  # yt-dlp raises many unrelated exception types
        raise RuntimeError(f"Search failed: {exc}") from exc

    if data is None:
        raise RuntimeError(f"Search failed: no results for {query!r}")

    results = []
    for entry in data.get("entries") or []:
        if not entry:
            continue
        results.append(
            {
                "title": entry.get("title") or "Unknown title",
                "url": entry.get("webpage_url")
                or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                "id": entry.get("id") or "",
                "duration": entry.get("duration") or 0,
            }
        )
    return results
