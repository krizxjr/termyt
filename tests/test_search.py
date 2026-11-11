"""Tests for ytm.

This first test is deliberately trivial: it checks that our package exposes
its version string. It never touches the network, so it always runs fast
and offline. As we add real modules (search, player), we'll add tests that
feed fake data through them instead of calling YouTube.
"""

import ytm
from ytm.search import format_duration


def test_version_is_a_string():
    assert isinstance(ytm.__version__, str)
    assert ytm.__version__ == "0.3.0"


def test_imports_smoke():
    """Every module must import cleanly — catches missing imports like a
    dropped `import time` before you ever run the app."""
    import ytm.__main__  # noqa: F401  (import is the test)
    import ytm.cli  # noqa: F401
    import ytm.player  # noqa: F401
    import ytm.search  # noqa: F401


def test_format_duration():
    assert format_duration(185) == "3:05"   # 3 minutes, 5 seconds
    assert format_duration(0) == "0:00"
    assert format_duration(None) == "0:00"  # live videos have no duration
    assert format_duration(3725) == "62:05"  # we don't bother with hours
