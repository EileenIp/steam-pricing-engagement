"""Stdout encoding. A cp1252 stdout killed a three-hour pull at game 97 of 3,497."""
from __future__ import annotations

import io

from src import console


class FakeStream:
    def __init__(self):
        self.calls = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)


def test_stdout_is_reconfigured_to_utf8_with_replacement():
    stream = FakeStream()
    console.use_utf8(stream)
    assert stream.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_a_stream_without_reconfigure_is_left_alone():
    # StringIO has no cp1252 problem, and must not raise here.
    console.use_utf8(io.StringIO())


def test_a_real_text_stream_then_encodes_the_name_that_broke_the_pull():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    console.use_utf8(stream)
    stream.write("Симулятор")  # the character class that raised UnicodeEncodeError
    stream.flush()


def test_every_entry_point_calls_it():
    import pathlib

    for name in ("playtime", "analysis", "cohort", "steamspy_fetch"):
        source = pathlib.Path(f"src/{name}.py").read_text(encoding="utf-8")
        assert "console.use_utf8()" in source, f"{name} would die on a non-ASCII title"
