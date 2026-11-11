"""Tests for next_index — the queue decision logic, kept pure so tests
can run offline with a seeded RNG (no player, no network, no threads)."""

import random

from ytm.cli import next_index


def test_linear_advance():
    assert next_index(0, 5, shuffle=False, loop=True) == 1
    assert next_index(2, 5, shuffle=False, loop=True) == 3


def test_linear_wraps_when_loop():
    assert next_index(4, 5, shuffle=False, loop=True) == 0


def test_linear_stops_when_no_loop():
    assert next_index(4, 5, shuffle=False, loop=False) == -1


def test_shuffle_never_repeats_current():
    rng = random.Random(42)
    for _ in range(100):
        nxt = next_index(2, 5, shuffle=True, loop=True, rng=rng)
        assert nxt in {0, 1, 3, 4}  # everything except the current 2


def test_shuffle_exercises_all_candidates_eventually():
    rng = random.Random(7)
    seen = {
        next_index(0, 4, shuffle=True, loop=True, rng=rng)
        for _ in range(200)
    }
    assert seen == {1, 2, 3}


def test_single_track_queue_always_replays_it():
    assert next_index(0, 1, shuffle=True, loop=True) == 0
    assert next_index(0, 1, shuffle=False, loop=False) == 0


def test_empty_queue_stops():
    assert next_index(0, 0, shuffle=True, loop=True) == -1
