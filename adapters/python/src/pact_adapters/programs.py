"""What a host is handed to run ONE carried program: its ceilings, read once (P6/P7).

`ir.ProgramSpec` is the program as a run is told about it — names, shapes, the
body's location and this. Kept in its own module because the reading of a
`program-fuel:` block is one grammar shared by every host that runs a body, and a
host that read `10m` its own way would hold a ceiling a hundred times wider or
narrower than the one the author wrote.

THE BODY CONTRACT. PACT never opens a body (R5, D17); what a host does with one
is the host's. But two hosts given the same program and the same inputs must
give the same answer, or the trace stops being the portability oracle — so the
shape of a run is written down here, once, for each engine a host may supply:

- `python`: the body folder holds one `.py` file (or `main.py` when there are
  several). It runs with one global, `inputs`, a mapping keyed by the program's
  own `takes:` names exactly as written (`inputs["purchased-on"]`). The value of
  its last expression is the answer: a mapping keyed by `answers-with:` names.
- `wasm`: the body folder holds one `.wasm` file (or `main.wasm`), a WASI command
  module. It reads the inputs as one JSON object on standard input and writes
  the answer as one JSON object on standard output, and nothing else there.
- `typescript`: no contract yet; a host that runs one says how.

What a run is handed back is the answer, held to `answers-with:` — a value that
does not fit is that call's failure and never a silent wrong number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .limits import seconds

__all__ = ["CEILINGS", "ProgramFuel", "body_entry", "size"]

#: The three ceilings, in the order the schema writes them. One tuple, so a host
#: that reports "this ceiling I cannot hold" and the reader below never disagree
#: about which there are.
CEILINGS: tuple[str, ...] = ("instructions-at-most", "runs-for-at-most", "memory-at-most")


def size(raw: Any) -> "int | None":
    """`10m`, `64m`, `32k`, `200000` — a `size` as a whole number.

    `k` is a thousand and `m` a million, the same spellings `needs.context-at-least`
    takes, because a schema type means one thing wherever it is written. `None`
    for anything that is not a size, never zero: a ceiling read as zero would stop
    every run at its first step, which is a different decision from the one the
    author made.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    text = str(raw).strip().lower().replace(",", "").replace("_", "")
    if not text:
        return None
    scale = 1
    if text.endswith("k"):
        scale, text = 1_000, text[:-1]
    elif text.endswith("m"):
        scale, text = 1_000_000, text[:-1]
    try:
        value = int(round(float(text) * scale))
    except ValueError:
        return None
    return value if value > 0 else None


@dataclass(frozen=True)
class ProgramFuel:
    """What one run of one program may spend before it is stopped (`fuel:`).

    `None` means the author wrote no such ceiling. `when_it_runs_out` is the
    author's word, `""` when they wrote none — which `pact check` refuses beside
    any ceiling (`needs-also`), so a host never has to guess between the three.
    """

    #: `instructions-at-most:`, counted the way the room counts work.
    instructions_at_most: "int | None" = None
    #: `runs-for-at-most:`, in seconds, through `limits.seconds`.
    runs_for_at_most: "float | None" = None
    #: `memory-at-most:`, in bytes (`64m` is 64 000 000).
    memory_at_most: "int | None" = None
    #: `stop-and-say-so`, `ask-a-person` or `answer-with-what-it-has`.
    when_it_runs_out: str = ""

    @staticmethod
    def from_document(raw: Any) -> "ProgramFuel":
        block = raw if isinstance(raw, Mapping) else {}
        return ProgramFuel(
            instructions_at_most=size(block.get("instructions-at-most")),
            runs_for_at_most=seconds(block.get("runs-for-at-most")),
            memory_at_most=size(block.get("memory-at-most")),
            when_it_runs_out=str(block.get("when-it-runs-out") or "").strip(),
        )

    def written(self) -> dict[str, "int | float"]:
        """The ceilings the author wrote, by their field names."""
        values = (self.instructions_at_most, self.runs_for_at_most, self.memory_at_most)
        return {name: v for name, v in zip(CEILINGS, values, strict=True) if v is not None}


def body_entry(files: "tuple[str, ...]", engine: str) -> str:
    """Which file of a body a host starts, by the contract above, or `""`.

    The one file of the engine's kind, or `main.<ext>` when there are several. A
    body with several and no `main` names nothing: picking one would be a guess
    about which file the author meant to run.
    """
    ext = {"python": ".py", "wasm": ".wasm", "typescript": ".ts"}.get(engine, "")
    if not ext:
        return ""
    mine = [f for f in files if f.endswith(ext)]
    if len(mine) == 1:
        return mine[0]
    main = f"main{ext}"
    return main if main in mine else ""
