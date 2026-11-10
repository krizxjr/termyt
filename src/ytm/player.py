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

Volume control doesn't use signals — signals can't carry values. Instead,
mpv exposes a tiny control protocol: give it --input-ipc-server:<socket>
and it creates a Unix socket (a filesystem object you can write JSON into)
that accepts commands like {"command": ["set_property", "volume", 90]}.
This changes volume instantly, mid-song, exactly at the speakers.

One quirk: since a stopped process can't answer us, "is something playing?"
is tracked in Python state, not by asking mpv.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import uuid
from pathlib import Path

from yt_dlp import YoutubeDL

# We only need metadata, so we tell yt-dlp to fetch as little as possible.
# "skip_download" never saves any audio to disk.
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
        set_volume(0..100) -> instant via IPC when playing
        stop()
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._paused = False
        self._current: dict[str, str] | None = None
        self._volume = 100
        self._ipc_path: Path | None = None

    @property
    def current(self) -> dict[str, str] | None:
        """The entry being played, or None if the player is idle."""
        return self._current

    @property
    def playing(self) -> bool:
        """True when sound is coming out right now (not paused, not ended)."""
        return self._proc is not None and not self._paused and self._poll() is None

    def play(self, entry: dict[str, str], volume: int | None = None) -> str:
        """Start playing `entry`; stop whatever was playing first."""
        self.stop()
        if volume is not None:
            self._volume = volume
        stream_url = self._resolve(entry["url"])
        args = [
            "mpv",
            "--no-video",
            "--no-terminal",
            f"--volume={self._volume}",
            stream_url,
        ]
        if self._ipc_setup():
            args.insert(1, f"--input-ipc-server={self._ipc_path}")
        try:
            self._proc = subprocess.Popen(args, stderr=subprocess.DEVNULL)
        except OSError:  # socket path failed?  fall back to signal-only mode
            self._ipc_path = None
            args = ["mpv", "--no-video", "--no-terminal",
                    f"--volume={self._volume}", stream_url]
            self._proc = subprocess.Popen(args, stderr=subprocess.DEVNULL)
        self._current = entry
        self._paused = False
        return entry["title"]

    def set_volume(self, volume: int) -> None:
        """Set volume, remembering it for the next play.

        When something is playing, this is a live IPC command — the song
        keeps going at the new loudness. Only when the IPC socket isn't
        available do we restart the track as a fallback.
        """
        volume = max(0, min(100, volume))  # clamp before anything else
        self._volume = volume
        if self._proc is not None and self._poll() is None and self._current:
            if self._ipc_path and self._ipc_alive() and self._ipc_command(
                ["set_property", "volume", volume]
            ):
                return  # done: instant, no restart
            self.play(self._current)  # fallback: restart with new --volume

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
        if self._ipc_path and self._ipc_path.exists():  # socket file cleanup
            try:
                self._ipc_path.unlink()
            except OSError:
                pass  # a leftover file in /tmp is harmless
        self._ipc_path = None

    def _poll(self) -> int | None:
        """Child's exit code, or None if still running."""
        return self._proc.poll() if self._proc else None

    # ----- mpv IPC (JSON over a Unix socket) --------------------------------

    def _ipc_setup(self) -> bool:
        """Decide and store the socket path for the *next* mpv launch."""
        # Unique per process AND per run: pid avoids collisions between
        # concurrent ytm instances; a few uuid chars avoid stale sockets
        # left behind by crashed previous runs reusing the same pid.
        self._ipc_path = Path(
            f"/tmp/termyt-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
        )
        return True

    def _ipc_alive(self) -> bool:
        """mpv creates the socket lazily at startup; give it up to 2s."""
        if self._ipc_path is None:
            return False
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if self._ipc_path.exists():
                try:  # socket file exists ≠ bind finished; a connect proves it
                    with socket.socket(socket.AF_UNIX) as s:
                        s.settimeout(0.2)
                        s.connect(str(self._ipc_path))
                    return True
                except OSError:
                    pass
            time.sleep(0.05)
        return False

    def _ipc_command(self, command: list) -> bool:
        """Send one mpv IPC command; return True if mpv says success."""
        if self._ipc_path is None:
            return False
        message = json.dumps({"command": command}) + "\n"
        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(2.0)
                sock.connect(str(self._ipc_path))
                sock.sendall(message.encode())
                # Responses arrive as JSON lines; events may interleave, so
                # read lines until one carries the "error" key.
                reply = b""
                while b'"error"' not in reply:
                    chunk = sock.recv(4096)
                    if not chunk:  # mpv hung up
                        return False
                    reply += chunk
        except OSError:
            return False
        try:
            first_line = reply.splitlines()[0].decode("utf-8", "replace")
            response = json.loads(first_line)
            return response.get("error") == "success"
        except (IndexError, ValueError, KeyError):
            return False

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
