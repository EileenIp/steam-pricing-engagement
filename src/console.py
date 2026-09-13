"""Console setup for the command-line entry points.

Windows gives redirected stdout a cp1252 encoding, which cannot represent most
of the Steam catalogue. That is not a theoretical problem: a single Cyrillic
character in a game title raised UnicodeEncodeError and killed a three-hour
playtime pull at game 97 of 3,497. The fetched data survived - every page is
cached before anything is printed - but the run did not.

So every entry point reconfigures stdout before printing, and sets
errors="replace" as well as UTF-8. A progress line is never worth losing a pull
over, and a game whose title will not encode should print as a row of question
marks rather than take the process down.
"""
from __future__ import annotations

import sys


def use_utf8(stream=None) -> None:
    """Make `stream` (default stdout) encode the whole catalogue without raising."""
    target = sys.stdout if stream is None else stream
    reconfigure = getattr(target, "reconfigure", None)
    if reconfigure is None:
        # Not a text stream that supports it (a StringIO in tests, say). Nothing
        # to do: those do not have the cp1252 problem in the first place.
        return
    reconfigure(encoding="utf-8", errors="replace")
