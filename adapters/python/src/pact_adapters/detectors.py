"""Detectors an author declares, beside the five built in (docs/98 WP-12).

`workspace.detectors:` names a thing and the patterns it looks like. Two readers
use them: a hiding sentence (`replace anything that looks like an order
reference with "[ref]"`), compiled by `interceptors`, and the condition word
`looks-like:`, read by `conditions.holds`. Both reach them through `DECLARED`,
set for as long as the thing reading them runs — a chain while it is built, a
workflow run, a board's admission check — so one workspace's detectors are
never another's.

Each detector's `examples:` are held against its own patterns when it is read,
so a pattern that misses the example its author wrote stops the run at the
start rather than letting that value through.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any, Mapping

#: Name -> one pattern (its `looks-like:` lines joined), for the workspace in hand.
DECLARED: "ContextVar[Mapping[str, str]]" = ContextVar("pact_detectors", default={})


class DetectorError(ValueError):
    """A detector whose patterns do not compile, or miss its own examples."""


def declared_in(doc: Mapping[str, Any]) -> dict[str, str]:
    """The workspace's `detectors:`, each as one pattern, held to its examples."""
    out: dict[str, str] = {}
    for name, body in (doc.get("detectors") or {}).items():
        if not isinstance(body, Mapping):
            continue
        lines = [str(p) for p in (body.get("looks-like") or []) if str(p).strip()]
        if not lines:
            continue
        try:
            pattern = "|".join(f"(?:{p})" for p in lines)
            compiled = re.compile(pattern)
        except re.error as err:
            raise DetectorError(
                f"the detector {name!r} looks like a pattern that cannot be read: {err}. "
                f"Fix its `looks-like:` lines."
            ) from None
        for example in body.get("examples") or []:
            if not compiled.search(str(example)):
                raise DetectorError(
                    f"the detector {name!r} does not recognise its own example "
                    f"{str(example)!r}, so it would let that value through. Fix its "
                    f"`looks-like:` lines, or the example."
                )
        out[str(name).strip().lower()] = pattern
    return out


def pattern_of(name: str) -> str | None:
    """The pattern for a thing by name: one the workspace declared, or built in."""
    key = str(name).strip().lower()
    declared = DECLARED.get()
    if key in declared:
        return declared[key]
    from .interceptors import RECOGNISES  # `interceptors` imports `conditions`

    return RECOGNISES.get(key)
