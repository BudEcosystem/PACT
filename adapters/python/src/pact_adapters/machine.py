"""What a model needs of the machine that runs it, and whether this machine has it.

A catalogue row may say how many parameters a model has (`size:`) and what a
machine needs to run it where it is served on that machine (`requires:
{memory, accelerator}`). A runtime that knows its machine leaves out a model
served only here that the machine cannot hold, with a sentence saying why; a
runtime that does not know, or a row that records nothing, leaves nothing out.

`spec/hardware-fit.yaml` holds the readings and the decisions, and the
checker (`crates/pact-loader/src/hardware.rs`) refuses a figure this module
could not read, where it is written.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

#: A parameter count: a number and an optional `K`, `M`, `B` or `T`
#: (thousand, million, billion, trillion), either case — `7.6B`, `405b`, `500M`.
_COUNT = re.compile(r"^(\d+(?:\.\d+)?)\s*([kKmMbBtT]?)$")
_COUNT_SCALE = {"": 1, "k": 10**3, "m": 10**6, "b": 10**9, "t": 10**12}

#: An amount of memory: a number and a unit, with or without a space between —
#: decimal `KB`, `MB`, `GB`, `TB` or binary `KiB`, `MiB`, `GiB`, `TiB`. A bare
#: number is refused: bytes and gigabytes differ by a factor nobody should guess.
_BYTES = re.compile(r"^(\d+(?:\.\d+)?)\s*([KMGT]i?B)$")
_BYTES_SCALE = {
    "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12,
    "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "TiB": 2**40,
}


def parameters_of(written: object) -> "float | None":
    """A `size:` figure's value as a number of parameters, or `None` when it does not read.

    `unknown` reads as `None` too; the checker tells the two apart.
    """
    if isinstance(written, bool) or not isinstance(written, str | int | float):
        return None
    match = _COUNT.match(str(written).strip())
    if match is None:
        return None
    count = float(match.group(1)) * _COUNT_SCALE[match.group(2).lower()]
    return count if count > 0 else None


def bytes_of(written: object) -> "int | None":
    """A `requires.memory:` figure's value in bytes, or `None` when it does not read."""
    if not isinstance(written, str):
        return None
    match = _BYTES.match(written.strip())
    if match is None:
        return None
    amount = round(float(match.group(1)) * _BYTES_SCALE[match.group(2)])
    return amount if amount > 0 else None


def shown(amount: int) -> str:
    """Bytes as a sentence prints them: gigabytes to one decimal, `.0` dropped — `8 GB`, `15.6 GB`."""
    text = f"{amount / 10**9:.1f}"
    return f"{text[:-2] if text.endswith('.0') else text} GB"


@dataclass(frozen=True)
class Machine:
    """What a runtime knows about the machine it runs on.

    `None` means the runtime does not know, and nothing is judged on it.
    `accelerator_memory_bytes` of `0` means the machine has no accelerator.
    """

    memory_bytes: "int | None" = None
    accelerator_memory_bytes: "int | None" = None


def this_machine() -> Machine:
    """The memory this process's machine reports. Its accelerator is not known here."""
    try:
        pages, size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, ValueError, OSError):  # a platform with no sysconf names
        return Machine()
    return Machine(memory_bytes=pages * size if pages > 0 and size > 0 else None)


def fits(memory_written: str, memory_bytes: "int | None", accelerator: str, machine: Machine) -> tuple[bool, str]:
    """Whether `machine` can run a model that needs `memory_bytes` (written `memory_written`).

    `accelerator` is the row's `requires.accelerator:` (`gpu` or `none`). A
    figure the row does not record, or a machine figure the runtime does not
    know, is never a reason to leave the model out.
    """
    if accelerator == "gpu":
        have = machine.accelerator_memory_bytes
        if have == 0:
            return False, "runs only on an accelerator, and this machine has none"
        if have is not None and memory_bytes is not None and memory_bytes > have:
            return False, f"needs {memory_written} of accelerator memory, and this machine has {shown(have)}"
        return True, ""
    have = machine.memory_bytes
    if have is not None and memory_bytes is not None and memory_bytes > have:
        return False, f"needs {memory_written} of memory, and this machine has {shown(have)}"
    return True, ""
