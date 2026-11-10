"""Entry point for `python -m ytm`.

Two ways to run ytm:
- `python -m ytm "some query"`     — one-shot demo: search, pick, play.
- `python -m ytm`                  — full interactive session (the real app).
"""

import sys
import time

from rich.console import Console
from rich.table import Table

from ytm import __version__
from ytm.cli import Session
from ytm.player import Player
from ytm.search import format_duration, search


console = Console()


def _demo_search(query: str) -> None:
    """One-shot mode kept from phase 3: useful for quick tests."""
    results = search(query)
    table = Table(show_header=True, header_style="bold cyan")
    for i, r in enumerate(results, start=1):
        table.add_row(str(i), r["title"], format_duration(r["duration"]))
    console.print(table)

    choice = console.input("[bold]Play which #? (1-5, Enter to skip) ")
    if choice.isdigit() and 1 <= int(choice) <= len(results):
        entry = results[int(choice) - 1]
        player = Player()
        player.play(entry)
        console.print(f"[green]Now playing[/green] {entry['title']} — Ctrl+C to skip")
        try:
            # Block until the song finishes (or Ctrl+C skips it).
            while player._proc and player._proc.poll() is None:
                time.sleep(0.5)
        except KeyboardInterrupt:
            player.stop()
            console.print("[red]Stopped.[/red]")


def main() -> None:
    if len(sys.argv) > 1:
        _demo_search(" ".join(sys.argv[1:]))
        return

    console.print(f"[bold]ytm[/bold] {__version__} — interactive session\n")
    try:
        Session().start()
    except KeyboardInterrupt:
        # Ctrl+C at a text prompt (Search:…) quits instead of crashing.
        console.print("[red]Stopped by you.[/red]")
    finally:
        console.print("[bold]Bye![/bold]")


if __name__ == "__main__":
    main()
