"""Audio playback driven by mpv as a child process.

The design: our Python program stays in charge, mpv does the hard part.

To play, we ask yt-dlp to resolve one video into a direct audio stream URL
(an mp4 containing only audio, streamed over HTTPS), then launch
`mpv --no-video <url>`. mpv handles downloading, buffering, and decoding —
we never touch any of that.

For controls we use POSIX *signals*, the standard way Unix processes
message each other:

- SIGSTOP freezes a process; SIGCONT unfreezes it. Since our player runs
  mpv in a child process, we remember its process id and simply stop and
  continue it for pause/resume.
- SIGTERM politely asks a process to exit; that's our stop button.

One quirk: since a stopped process can't answer us, "is something playing?"
is tracked in Python state, not by asking mpv.
"""

from __future__ import annotations

import signal
import subprocess

from yt_dlp import YoutubeDL

# Like search.py's options, but we need full extraction so yt-dlp resolves
# the actual stream URL, and "bestaudio" means we ask for audio only.
_EXTRACT_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "format": "bestaudio",
}


class Player:
    """Owns exactly one mpv child process at a time.

    Public interface:
        play(entry) -> start playing a search-result dict {"title", "url", ...}
        pause() / resume() / toggle()
        stop()
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._paused = False
        self._current: dict[str, str] | None = None

    @property
    def current(self) -> dict[str, str] | None:
        """The entry being played, or None if the player is idle."""
        return self._current

    @property
    def playing(self) -> bool:
        """True when sound is coming out right now (not paused, not ended)."""
        return self._proc is not None and not self._paused and self._poll() is None

    def play(self, entry: dict[str, str]) -> str:
        """Start playing `entry`; stop whatever was playing first."""
        self.stop()
        stream_url = self._resolve(entry["url"])
        self._proc = subprocess.Popen(
            [
                "mpv",
                "--no-video",
                "--no-terminal",
                stream_url,
            ]
        )
        self._current = entry
        self._paused = False
        return entry["title"]

    def pause(self) -> None:
        if self._proc and not self._paused and self._poll() is None:
            self._proc.send_signal(signal.SIGSTOP)
            self._paused = True

    def resume(self) -> None:
        if self._proc and self._paused:
            self._proc.send_signal(signal.SIGCONT)
            self._paused = False

    def toggle(self) -> None:
        """Pause if playing, resume if paused."""
        if self._paused:
            self.resume()
        else:
            self.pause()

    def stop(self) -> None:
        """End playback and reap the child process."""
        if self._proc is None:
            self._current = None
            return
        if self._poll() is None:  # still running: kill it
            if self._paused:  # a stopped process can't receive SIGTERM
                self.resume()
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:  # stubborn child
                self._proc.kill()
                self._proc.wait()
        self._proc = None
        self._current = None
        self._paused = False

    def _poll(self) -> int | None:
        """Child's exit code, or None if still running."""
        return self._proc.poll() if self._proc else None

    @staticmethod
    def _resolve(webpage_url: str) -> str:
        """Turn a YouTube watch URL into a direct audio stream URL."""
        with YoutubeDL(_EXTRACT_OPTIONS) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
        if not info or not info.get("url"):
            raise RuntimeError(f"Could not resolve a stream for {webpage_url}")
        return info["url"]

    def __del__(self) -> None:
        # Safety net if the app exits mid-song; stop() is the real control.
        self.stop()
