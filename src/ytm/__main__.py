"""Entry point for `python -m ytm`.

Phase 3 demo: search, pick a number, hear music from your speakers.
The interactive loop (pause, volume, next, quit) is the next phase.
"""

import sys
import time

from rich.console import Console

from rich.table import Table

from ytm import __version__
from ytm.player import Player
from ytm.search import format_duration, search


console = Console()


def _demo_search(query: str) -> None:
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
            # Block this demo until the song finishes or mpv exits.
            while player._proc and player._proc.poll() is None:
                time.sleep(0.5)
        except KeyboardInterrupt:
            player.stop()
            console.print("[red]Stopped.[/red]")


def main() -> None:
    if len(sys.argv) > 1:
        _demo_search(" ".join(sys.argv[1:]))
        return

    console.print(f"[bold]ytm[/bold] {__version__}")
    console.print('Usage: python -m ytm "search terms"')


if __name__ == "__main__":
    main()
