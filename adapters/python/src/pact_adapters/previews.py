"""A value shown to a model in a few words, and whole everywhere else.

`docs/100` §5, from NOOA: how much data an agent can work on is set by where
the work is carried out, not by how much a model can read. A value handed to a
model by reference stays whole in the run; what the model is SHOWN is a
preview with a fixed, small size, so a list of a million rows costs what a list
of a hundred does.

One rule makes a preview safe to read: **a value written out plainly is
complete, and a value that has been cut says so, with its true size.** There is
no second channel for "was this cut?". `GRAMMAR` is told to the model once.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

#: What a model is told, once, about how values are shown to it.
GRAMMAR = (
    "How values are shown to you. A value written out plainly is complete. A value "
    "that is too long to show is written `list(N items; first: …; last: …)`, "
    "`text(N characters; begins: …; ends: …)` or `record(N fields; …)`: N is its "
    "true size, and what follows is a sample, not the value. You cannot read the "
    "rest by looking; write steps that work on it by its name, and the steps are "
    "carried out on the whole value."
)

#: Shown whole at or under these sizes.
ITEMS, CHARACTERS = 6, 160


def preview(value: Any, *, items: int = ITEMS, characters: int = CHARACTERS) -> str:
    """`value` as a model is shown it: whole when it is small, and otherwise
    its kind, its true size and a sample from each end."""
    if isinstance(value, str):
        if len(value) <= characters:
            return json.dumps(value, ensure_ascii=False)
        cut = characters // 4
        return (
            f"text({len(value)} characters; begins: {json.dumps(value[:cut], ensure_ascii=False)}; "
            f"ends: {json.dumps(value[-cut:], ensure_ascii=False)})"
        )
    if isinstance(value, (list, tuple)):
        if len(value) <= items:
            return "[" + ", ".join(preview(v, items=items, characters=characters // 2) for v in value) + "]"
        head = ", ".join(preview(v, items=2, characters=characters // 4) for v in value[:2])
        tail = preview(value[-1], items=2, characters=characters // 4)
        return f"list({len(value)} items; first: {head}; last: {tail})"
    if isinstance(value, Mapping):
        if len(value) <= items:
            inner = ", ".join(
                f"{json.dumps(str(k))}: {preview(v, items=items, characters=characters // 2)}"
                for k, v in value.items()
            )
            return "{" + inner + "}"
        names = ", ".join(str(k) for k in list(value)[:items])
        return f"record({len(value)} fields; {names}, …)"
    return json.dumps(value, ensure_ascii=False, default=str)


def is_cut(shown: str) -> bool:
    """Whether a preview says its value was cut."""
    return any(mark in shown for mark in ("list(", "text(", "record("))
