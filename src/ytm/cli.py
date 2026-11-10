"""The interactive command loop for ytm.

How it works, in one paragraph: we keep a `queue` (a plain Python list of
search results) and an index pointing at the track we're on. The main loop
blocks waiting for a single keypress (via the tiny `readchar` library),
acts on it — pause, next, volume, search, quit — then repeats. A background
thread watches the mpv child process and, when a song finishes by itself,
advances the queue.

The background thread is why nothing needs to poll in a busy loop: the
main thread waits on the keyboard, the watcher thread waits on the child
process, and they meet only when one of them changes playback state.
"""

from __future__ import annotations

import threading

import readchar
from rich.console import Console
from rich.table import Table

from ytm.player import Player
from ytm.search import format_duration, search
from ytm import state

console = Console()

# The only secret to good UX here: print the menu whenever the state so
# far has scrolled away from the user.
_MENU = (
    "\n[bold cyan]Controls[/bold cyan]  "
    "p=pause/resume  n=next  b=previous  s=search  "
    "+=/- volume  q=quit\n"
)


class Session:
    """One interactive run of ytm: queue, player, and the key loop."""

    def __init__(self) -> None:
        self.player = Player()
        self.player.set_volume(80)  # default takes over at next play
        self.queue: list[dict] = []
        self.index = -1  # position in queue; -1 = nothing selected
        self._watcher: threading.Thread | None = None
        self._generation = 0  # bumped on every manual action; see _watch
        self._stopping = False  # True when the user quit the session

    # -- playback plumbing -------------------------------------------------

    def _watch(self, generation: int, proc, on_end) -> None:
        """Wait for THIS child proc to end; if nobody replaced it, advance.

        The generation counter is what stops races: suppose you press 'n'
        (next) while the watcher for the *previous* song is still waiting
        on its process. The old watcher wakes up, sees the generation has
        moved on, and quietly gives up.
        """
        if proc is not None:
            proc.wait()
        if generation == self._generation and not self._stopping:
            console.print("[dim](track finished)[/dim]")
            on_end()

    def _play_index(self, i: int) -> None:
        self.index = i
        self._generation += 1
        title = self.player.play(self.queue[i])
        console.print(f"[green]▶[/green] {i + 1}/{len(self.queue)} {title}")
        self._start_watcher()

    def _start_watcher(self) -> None:
        """Spawn the thread that auto-advances when the current mpv exits.

        The watcher pairs with the generation counter: whenever something
        replaces playback (skip, volume restart, quit), the generation is
        bumped first so the stale watcher's wake-up matches nothing and it
        exits silently instead of acting on a dead proc.
        """
        gen = self._generation
        proc = self.player._proc  # the NEW process is the one to watch
        t = threading.Thread(
            target=self._watch,
            args=(gen, proc, self._next_track),
            daemon=True,
        )
        t.start()
        self._watcher = t

    def _next_track(self, wrap: bool = True) -> None:
        if not self.queue:
            return
        nxt = self.index + 1
        if nxt >= len(self.queue):
            if wrap:  # loop back to the top of the queue
                nxt = 0
            else:
                console.print("[dim]End of queue.[/dim]")
                return
        self._play_index(nxt)

    def _previous_track(self) -> None:
        if not self.queue:
            return
        prev = self.index - 1
        if prev < 0:
            prev = len(self.queue) - 1
        self._play_index(prev)

    # -- user commands -----------------------------------------------------

    def start(self) -> None:
        """Restore a saved session if there is one; then loop."""
        saved = state.load()
        if saved["entries"]:
            self.queue = saved["entries"]
            self.player.set_volume(saved["volume"])
            console.print(
                f"[dim]Restored {len(self.queue)} tracks "
                f"from your last session.[/dim]"
            )
            if 0 <= saved["index"] < len(self.queue):
                self._play_index(saved["index"])  # resume where we left off
            else:
                self._next_track()  # queue exists, cursor lost: start at top
        self.do_search()
        self.loop()

    def do_search(self) -> None:
        query = console.input("[bold]Search: [/bold]")
        if not query.strip():
            return
        with console.status("[bold]Searching…"):
            try:
                results = search(query)
            except RuntimeError as exc:
                console.print(f"[red]{exc}[/red]")
                return
        if not results:
            console.print("[yellow]No results.[/yellow]")
            return
        table = Table(show_header=True, header_style="bold cyan")
        for i, r in enumerate(results, start=1):
            table.add_row(str(i), r["title"], format_duration(r["duration"]))
        console.print(table)
        console.print("[dim]These replace your queue.[/dim]")
        self.queue = results
        self.index = -1  # old cursor pointed into the old queue

        pick = console.input("[bold]Play which #? (Enter to skip) [/bold]")
        if pick.isdigit() and 1 <= int(pick) <= len(self.queue):
            self._play_index(int(pick) - 1)

    def loop(self) -> None:
        console.print(_MENU)
        while not self._stopping:
            key = readchar.readkey()
            if key in ("q", "\x03"):  # \x03 is Ctrl+C
                break
            elif key == "p":
                was = self.player._paused
                self._generation += 1
                self.player.toggle()
                console.print("[dim]paused[/dim]" if not was else "[dim]resumed[/dim]")
            elif key == "n":
                self.stop_current()
                self._next_track()
            elif key == "b":
                self.stop_current()
                self._previous_track()
            elif key == "s":
                self.stop_current()
                self.do_search()
            elif key in ("=", "+"):
                self._generation += 1  # old watcher is stale either way:
                # IPC path keeps the same proc (watcher must be replaced
                # because its generation no longer matches); fallback path
                # restarts the proc. Both need a fresh watcher.
                self.player.set_volume(self.player._volume + 10)
                self._start_watcher()
                console.print(f"[dim]volume → {self.player._volume}[/dim]")
            elif key == "-":
                self._generation += 1
                self.player.set_volume(self.player._volume - 10)
                self._start_watcher()
                console.print(f"[dim]volume → {self.player._volume}[/dim]")

    def stop_current(self) -> None:
        """Manual navigation: bump the generation so the old watcher quits."""
        self._generation += 1
        self.player.stop()

    def quit(self) -> None:
        """Persist the session, then shut down playback."""
        state.save(self.queue, index=self.index, volume=self.player._volume)
        self._stopping = True
        self._generation += 1
        self.player.stop()
