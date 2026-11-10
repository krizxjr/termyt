"""Entry point for `python -m ytm`.

This file lets you run the package as a program directly from the command
line. Python looks for a module named `__main__` inside a package when you
type `python -m <package>`. Right now it just prints a version banner so we
can prove the packaging works; the real menu loop arrives in a later phase.
"""

from ytm import __version__


def main() -> None:
    print(f"ytm {__version__} works!")


if __name__ == "__main__":
    main()
