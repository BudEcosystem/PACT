"""`explode` — a document back into the tree it came from (AC-1.2′).

> For every document whose field keys lie in the **portable key alphabet**
> (`^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$`, ≤64 bytes, NFC, excluding Windows
> reserved device names and names ending in `.` or space),
> `load(explode(D)) ≡ D` up to canonicalisation. For any key outside it,
> `explode` MUST fail loudly naming the offending field and MUST NOT emit a tree.

The loader turns a tree into a document. This turns a document back into a tree,
and the round trip is what makes the Expansion Rule a property rather than a
description: a format whose two directions do not compose has one direction and a
claim.

**The alphabet is checked first, over the WHOLE document, before a byte is
written.** The criterion says `MUST NOT emit a tree`, and that is not fussiness:
a key like `CON` or `a/b` or one ending in a space produces a directory that
cannot be created on some machine, cannot be read back on others, or silently
becomes a different name. Half a tree on disk is worse than none, because the
half that wrote looks like it worked.

**Verified against the real loader, not against itself.** `load` here means the
Rust CLI. An `explode` checked by a Python re-implementation of the loader would
prove the two agreed with each other, which is the failure this repository has
found more than once.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .loader import FIX as LOADER_FIX
from .loader import pact_binary

#: The portable key alphabet, verbatim from AC-1.2′.
PORTABLE = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")

#: The longest a key may be, in BYTES rather than characters. A 64-character key
#: of three-byte glyphs is 192 bytes, and the filesystems this has to survive
#: count bytes.
LONGEST = 64

#: Names Windows reserves for devices, at any extension. `CON.yaml` is not a
#: file on Windows; it is the console, and writing to it succeeds and stores
#: nothing — the worst possible failure for a format whose whole claim is that
#: the tree IS the specification.
RESERVED = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{n}" for n in range(1, 10)),
    *(f"lpt{n}" for n in range(1, 10)),
})

#: Fields written as prose (`.md`) rather than settings. These are the ones an
#: author edits as text, and round-tripping them through YAML would turn a
#: paragraph into a quoted scalar with escaped newlines.
PROSE = frozenset({"instructions", "content", "description"})

#: Prose fields that stay in the settings file anyway, because they are one line
#: and a file per sentence is not a tree anybody wants to read.
STAYS_INLINE = frozenset({"description"})


#: The key the loader puts on a payload folder — a directory it carried
#: verbatim rather than read as fields.
PAYLOAD = "$payload"


class ExplodeRefused(Exception):
    """A document that cannot become a tree. Nothing was written."""


class CarriesPayloads(ExplodeRefused):
    """The document REFERENCES files it does not contain.

    A payload — `skills/refund-policy/scripts/`, `references/` — is a directory
    the loader carried verbatim, and what reaches the document is a reference:
    the path, the size, the content type. **Not the bytes.** So `explode` cannot
    reproduce that part of the tree from the document alone, and
    `load(explode(D)) ≡ D` is simply not available for such a D.

    Reported as its own refusal rather than folded into the alphabet one,
    because the two need different answers. An unportable key is renamed; this is
    told *"explode the tree you still have, or fetch the payload files"*. Calling
    both "not portable" would send somebody renaming `$payload`, which is not
    theirs to rename.
    """


@dataclass
class Explosion:
    """What `explode` wrote, and what it refused to."""

    root: Path
    wrote: list[str] = field(default_factory=list)
    #: `{key path: why it is not portable}` — populated only on a refusal, and
    #: then nothing is written at all.
    refused: dict[str, str] = field(default_factory=dict)


def why_not_portable(key: str) -> str:
    """Why this key cannot be a file or directory name, or `""` if it can."""
    if key != unicodedata.normalize("NFC", key):
        return "not in NFC — the same name would compare unequal on macOS and Linux"
    if len(key.encode("utf-8")) > LONGEST:
        return f"{len(key.encode('utf-8'))} bytes, and {LONGEST} is the limit"
    if key.endswith(".") or key.endswith(" "):
        return (
            "ends in a dot or a space, which Windows silently strips — the name "
            "read back would not be the name written"
        )
    if key.split(".")[0].lower() in RESERVED:
        return (
            "a Windows reserved device name. Writing to it succeeds and stores "
            "nothing, which is the worst failure a format whose tree IS the "
            "specification can have"
        )
    if not PORTABLE.match(key):
        return (
            "outside the portable key alphabet "
            "`^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$` — a name that survives every "
            "filesystem this has to cross"
        )
    return ""


def _payload_paths(node: Any, at: tuple[str, ...] = ()) -> list[str]:
    """Every payload reference in the document, by path."""
    found: list[str] = []
    if isinstance(node, Mapping):
        if PAYLOAD in node:
            return [".".join(at) or PAYLOAD]
        for key, value in node.items():
            found += _payload_paths(value, (*at, str(key)))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found += _payload_paths(value, (*at, str(i)))
    return found


def _unportable(node: Any, at: tuple[str, ...] = ()) -> dict[str, str]:
    """Every key in the document that cannot become a name, by path."""
    found: dict[str, str] = {}
    if isinstance(node, Mapping):
        for key, value in node.items():
            why = why_not_portable(str(key))
            if why:
                found[".".join((*at, str(key)))] = why
            found.update(_unportable(value, (*at, str(key))))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.update(_unportable(value, (*at, str(i))))
    return found


def _yaml(value: Any) -> str:
    import yaml

    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True)


def explode(document: Mapping[str, Any], into: "str | Path") -> Explosion:
    """One document as a file tree the loader reads back identically.

    Refuses first and writes second. `_unportable` walks the WHOLE document
    before anything is created, because the criterion says `MUST NOT emit a
    tree` — and half a tree on disk is worse than none, since the half that wrote
    looks like it worked.
    """
    root = Path(into)

    # PAYLOADS FIRST, because the answer is different. A document referencing
    # files it does not carry cannot become the tree it came from at all, and
    # saying "these keys are not portable" would send somebody renaming `$payload`
    # — a key the loader wrote, not the author.
    carried = _payload_paths(document)
    if carried:
        raise CarriesPayloads(
            "this document references payload files it does not contain, so the "
            "tree cannot be rebuilt from it, and nothing was written:\n"
            + "\n".join(f"  {p}" for p in sorted(carried))
            + "\n\nFix: explode a document with no payloads, or rebuild those "
              "folders from wherever the files actually are. A payload is bytes "
              "the loader carried verbatim; what reaches a document is a "
              "reference to them."
        ) from None

    bad = _unportable(document)
    if bad:
        raise ExplodeRefused(
            "this document cannot be written as a tree, and nothing was written:\n"
            + "\n".join(f"  {k}: {why}" for k, why in sorted(bad.items()))
            + "\n\nFix: rename each field to lower-case letters, digits, dots, "
              "dashes and underscores, at most 64 bytes, not ending in a dot or "
              "a space."
        ) from None
    root.mkdir(parents=True, exist_ok=True)
    said = Explosion(root=root)
    _write_map(dict(document), root, said, top=True)
    return said


def _write_map(node: dict, where: Path, said: Explosion, *, top: bool) -> None:
    """One mapping as a directory: prose to `.md`, the rest to a settings file.

    Nested maps become directories with their own settings file, which is the
    Expansion Rule read backwards — *a field may be a directory*.
    """
    settings: dict[str, Any] = {}
    for key, value in node.items():
        if key in PROSE and key not in STAYS_INLINE and isinstance(value, str):
            path = where / f"{key}.md"
            path.write_text(value if value.endswith("\n") else value + "\n")
            said.wrote.append(str(path))
            continue
        if isinstance(value, dict) and value and all(
            isinstance(v, dict) for v in value.values()
        ):
            # A map OF maps is a folder of things — `agents/`, `tools/`. A map of
            # scalars is one thing's settings and stays inline, which is why the
            # test is on the values and not on the key.
            folder = where / key
            folder.mkdir(parents=True, exist_ok=True)
            for name, inner in value.items():
                child = folder / name
                child.mkdir(parents=True, exist_ok=True)
                _write_map(dict(inner), child, said, top=False)
            continue
        settings[key] = value

    # `settings or top`, and the second half is not belt-and-braces. A workspace
    # with no `workspace.yaml` is one the loader warns about by name —
    # *"has an agent in it and no workspace around it, so nothing can find it:
    # `pact discover` returns none and `pact card` cannot publish it"* — so the
    # top file is written even when every top-level field turned out to be prose
    # or a folder.
    #
    # This read `settings or not said.wrote`, which asked whether ANYTHING had
    # been written anywhere yet: a global question standing in for a local one.
    # It gave the right answer for every valid document by accident — the first
    # thing written is always prose, so the flag was always false by the time it
    # was read — and produced a workspace with no `workspace.yaml` for a document
    # whose only top-level field was prose.
    if settings or top:
        name = "workspace.yaml" if top else "_index.yaml"
        path = where / name
        path.write_text(_yaml(settings))
        said.wrote.append(str(path))


USAGE = """\
pact-explode — write a document back out as the tree it came from

USAGE:
    pact-explode SOURCE INTO

SOURCE is a workspace `pact show` can read, or a `.json` document. INTO must not
exist: writing into a folder that already has files would merge two trees and
neither would be the one you asked for.

Refuses, and writes nothing, when a field key cannot become a file name, or when
the document references payload files it does not carry.
"""


def main(argv: "list[str] | None" = None) -> int:
    import json
    import subprocess
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0 if args and args[0] in ("-h", "--help") else 1

    source, into = Path(args[0]), Path(args[1])
    if into.exists():
        sys.stderr.write(
            f"error: {into} already exists, and writing into it would merge two "
            f"trees.\n  fix: name a folder that does not exist yet.\n"
        )
        return 1
    if source.suffix == ".json":
        document = json.loads(source.read_text())
    else:
        binary = pact_binary()
        if binary is None:
            sys.stderr.write(
                "error: the loader was not found, and a workspace is read through "
                f"it.\n  fix: {LOADER_FIX}, or pass a .json document.\n"
            )
            return 3
        shown = subprocess.run(
            [str(binary), "show", str(source)], capture_output=True, text=True
        )
        if shown.returncode != 0:
            sys.stderr.write(shown.stdout + shown.stderr)
            return 1
        document = json.loads(shown.stdout)

    try:
        said = explode(document, into)
    except ExplodeRefused as refused:
        sys.stderr.write(f"error: {refused}\n")
        return 1
    sys.stdout.write(f"Wrote {len(said.wrote)} file(s) into {into}.\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
