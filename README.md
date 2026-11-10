# ytm

A minimal terminal-based YouTube music player. Search YouTube and play the
audio directly in your terminal — no login, no OAuth, no API keys.

> **Status:** work in progress. This is a learning project.

## Legal note

`ytm` streams YouTube content for **personal use only** using `yt-dlp`.
It does not download, store, or redistribute any media. Using YouTube
without its official API sits in a gray area of YouTube's Terms of Service —
keep this personal and supported player usage in mind.

## Install

Requires Python 3.10+ and [mpv](https://mpv.io):

```bash
# KDE Neon / Ubuntu / Debian
sudo apt install mpv

# macOS (Homebrew)
brew install mpv
```

Then, from a clone of this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
python -m ytm
```

(needs an interactive player — coming in the next phases)

## Roadmap

- [x] Project skeleton with packaging and tests
- [ ] Search YouTube via yt-dlp
- [ ] Play via mpv subprocess
- [ ] Interactive prompt loop: pause/resume, volume, next/previous, quit
- [ ] Polished README, docs, more tests

## License

MIT — see [LICENSE](LICENSE).
