# ytm

A minimal terminal-based YouTube music player. Search YouTube, queue
results, and listen — entirely from your terminal. No login, no OAuth,
no API keys.

No video is ever shown or downloaded: ytm asks yt-dlp for an audio-only
stream and hands it to [mpv](https://mpv.io) to play.

## Features

- Search YouTube and get a numbered list of results
- Audio-only playback via mpv (pause/resume, instant volume via IPC,
  next/previous, automatic advance through the queue)
- Session persistence: your queue is saved on quit and restored next run
- Desktop integration (MPRIS over D-Bus on Linux): KDE/GNOME media
  widgets and keyboard media keys show the track and control playback
- Simple single-key interface; `s` for a fresh search at any time
- Personal-use only: nothing is ever saved to disk (state metadata only)

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
| `+` / `-` | volume up / down by 10 (instant, no restart) |
| `q` or `Ctrl+C` | quit (kills mpv too, no orphans) |

When a song finishes on its own, the next one starts automatically. The
media-widget repeat button switches looping on/off (on by default); with
looping off the queue stops at the end.

## How it works

- `ytm.search` — yt-dlp wrapper; finds videos and turns them into simple
  `{title, url, id, duration}` dicts. All YouTube coupling lives here.
- `ytm.player` — owns a single mpv child process. Resolves the audio
  stream with yt-dlp at play time (stream URLs expire, so late resolves
  are correct, not lazy). Pause = SIGSTOP, resume = SIGCONT, stop =
  SIGTERM. Volume goes over mpv's JSON IPC socket — instant, no restart.
- `ytm.cli` — the interactive loop. Blocks on single keypresses; uses a
  generation-counter guard so a leftover auto-advance watcher from a
  replaced track can never fire twice. Owns a daemon thread that watches
  the mpv process for natural song end.
- `ytm.mpris` — exports the MPRIS media-player interface on the session
  D-Bus, so desktop shells and media keys can drive ytm (Linux only;
  skipped gracefully when no session bus exists).
- `ytm.state` — queue persistence: JSON state under the XDG config
  directory (`~/.config/termyt/`), atomic writes, load failure reading
  as "no state".

## Known limitations

- Shuffle isn't implemented yet (widget toggle is accepted as a no-op
  so it doesn't error; real shuffle is a roadmap item).
- Search extracts flat results only; very long playlists can't be queued yet.
- Desktop integration covers Linux (MPRIS). Windows/macOS run fine but
  have no media-widget integration (different OS protocols entirely).
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
- [x] Interactive key-prompt player (v0.1)
- [x] Queue persistence (v0.2)
- [x] Instant volume via mpv IPC (v0.2)
- [x] MPRIS desktop integration (v0.2)
- [ ] Real shuffle
- [ ] Cosmetic progress display (position from IPC)

## License

MIT — see [LICENSE](LICENSE).
