"""Tests for ytm.

This first test is deliberately trivial: it checks that our package exposes
its version string. It never touches the network, so it always runs fast
and offline. As we add real modules (search, player), we'll add tests that
feed fake data through them instead of calling YouTube.
"""

import ytm


def test_version_is_a_string():
    assert isinstance(ytm.__version__, str)
    assert ytm.__version__ == "0.1.0"
