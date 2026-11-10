# ytm

A minimal terminal-based YouTube music player. Search YouTube, queue
results, and listen — entirely from your terminal. No login, no OAuth,
no API keys.

No video is ever shown or downloaded: ytm asks yt-dlp for an audio-only
stream and hands it to [mpv](https://mpv.io) to play.

## Features

- Search YouTube and get a numbered list of results
- Audio-only playback via mpv (controls: pause/resume, volume,
  next/previous, automatic advance through the queue)
- Simple single-key interface; `s` for a fresh search at any time
- Personal-use only: nothing is ever saved to disk

## Install

Requires Python 3.10+ and mpv.

```bash
# KDE Neon / Ubuntu / Debian
sudo apt install mpv

# macOS (Homebrew)
brew install mpv

# Windows: winget install mpv   (then make sure mpv is on PATH)
```

From a clone of this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```

## Usage

```bash
ytm              # full interactive session
# or
python -m ytm    # same thing, without the entry-point script
# or
python -m ytm "query"   # one-shot: search, pick a number, play
```

| Key | Action |
|-----|--------|
| `s` | new search (paste: type query, Enter, pick #) |
| `p` | pause / resume |
| `n` / `b` | next / previous track |
| `+` / `-` | volume up / down by 10 |
| `q` or `Ctrl+C` | quit (kills mpv too, no orphans) |

When a song finishes on its own, the next one starts automatically,
looping back to the top of the queue after the last track.

## How it works

- `ytm.search` — yt-dlp wrapper; finds videos and turns them into simple
  `{title, url, id, duration}` dicts. All YouTube-coupling lives here.
- `ytm.player` — owns a single mpv child process. Resolves the audio
  stream with yt-dlp at play time (stream URLs expire, so late resolves
  are correct, not lazy). Pause = SIGSTOP, resume = SIGCONT,
  stop = SIGTERM to the child.
- `ytm.cli` — the interactive loop. Blocks on single keypresses and uses
  a generation-counter guard so a leftover auto-advance watcher from a
  replaced track can never fire twice.

## Known limitations

- Volume changes restart the current track from the beginning
  (upgrading to mpv's IPC interface is the fix; traded for simplicity
  in v1).
- KDE/desktop media hubs (MPRIS) don't show track info, because mpv
  runs bare with `--no-terminal`. Enabling `--media-controls` is on the
  roadmap.
- Search extracts flat results only; very long playlists can't be
  queued yet.
- Like every yt-dlp-based tool: when YouTube changes, updating is
  usually just `pip install -U yt-dlp`.

## Legal note

ytm streams YouTube content for **personal use only** via yt-dlp; it
does not download, store, or redistribute any media. Using YouTube
without its official API sits in a gray area of YouTube's Terms of
Service — keep this to personal, non-redistributing use.

## Roadmap

- [x] Project skeleton with packaging and tests
- [x] yt-dlp search returning numbered results
- [x] Play selected result via mpv subprocess
- [x] Interactive loop: pause, volume, next/previous, auto-advance
- [ ] IPC-based volume (no restart on change)
- [ ] MPRIS desktop integration
- [ ] Saved queue / simple playlists persisted to a file

## License

MIT — see [LICENSE](LICENSE).
