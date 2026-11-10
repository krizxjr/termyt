"""Entry point for `python -m ytm`.

For phase 2 this file is a demo of the search module:
`python -m ytm "query here"` prints a numbered list of results.
The interactive menu replaces this in a later phase.
"""

import sys

from rich.console import Console
from rich.table import Table

from ytm import __version__
from ytm.search import format_duration, search


def _demo_search(query: str) -> None:
    """Run a search and print results as a numbered table."""
    console = Console()
    with console.status(f"[bold]Searching YouTube for {query!r}…"):
        results = search(query)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("Title")
    table.add_column("Time", justify="right")
    for i, r in enumerate(results, start=1):
        table.add_row(str(i), r["title"], format_duration(r["duration"]))
    console.print(table)


def main() -> None:
    if len(sys.argv) > 1:
        _demo_search(" ".join(sys.argv[1:]))
        return

    console = Console()
    console.print(f"[bold]ytm[/bold] {__version__} — playlist demo")
    console.print(
        "Usage: python -m ytm \"search terms\"\n"
        "(The interactive player arrives in a later phase.)"
    )


if __name__ == "__main__":
    main()
