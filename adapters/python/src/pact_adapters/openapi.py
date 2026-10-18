"""An OpenAPI description as one reviewed PACT tool file per operation (decision P10).

`pact-import --as openapi FILE [--out DIR]`. PACT has no OpenAPI reach (a tool
reaches through `connect:`, `url:` or `says:`), and reading the description at
run time would make tools that no tool file declares, so nobody would have
reviewed what each one does. So the description is IMPORTED: each operation
becomes `tools/<operation-id>.yaml`, a `url:` tool with one action named for
its `method:`, which a person reads and commits like any other tool file.

What each operation becomes:

* `url: <api>/<path>`: `<api>` is the API's title in kebab case, a name the
  host binds to the API's address (and to a client carrying its credentials:
  the description's security schemes are named in a comment and in the
  report, never as a value); `{name}` in the path is filled from the argument
  of that name;
* `takes:`: the path's parameters, then the query's for `get` and `delete`, or
  the JSON body's parts for `post`, `put` and `patch`, in PACT's shape words
  (`openapi_shapes.py`); a part that is an object is a named shape, added to
  `workspace.yaml`'s `shapes:` when the files are written;
* `answers-with:` from the success answer, when PACT can say all of it
  (`openapi_shapes.Line.whole`);
* `reads-only:` ONLY when the description declares it, with the extension
  `x-pact-reads-only: true` (or `false`) on the operation. Nothing is guessed
  from the method: a `get` that changes something exists. An operation that
  declares nothing gets no `reads-only:` and a *Needs a look* comment, so it
  is a write that cannot be undone until a person decides what it does.

The `ImportReport` names every key it read (S1: no silent drops): an operation,
each of its parameters, its body, its answers, and every schema keyword
beneath them, mapped, not portable (PACT has no home for it, and why), or
unmapped (what it was).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .importing import ImportReport
from .openapi_operations import TOP, Operations
from .openapi_shapes import Shapes, kebab

__all__ = ["Imported", "NotImported", "from_openapi", "write_into"]


class NotImported(ValueError):
    """The description, or the folder to write into, cannot be used as it is; says the fix."""


@dataclass
class Imported:
    """What one OpenAPI description became."""

    #: The name every `url:` begins with, which the host binds to the API's address.
    api: str
    #: `{"tools/<name>.yaml": text}`; bytes for a file copied as it is (a skill's asset).
    files: dict[str, str | bytes]
    #: `{shape name: {part: line}}`, for `workspace.yaml`'s `shapes:`.
    shapes: dict[str, dict[str, str]]
    report: ImportReport
    #: The tools whose description declares no effect.
    needs_a_look: tuple[str, ...] = ()
    #: The API's address as the description gives it (`servers[0].url`), or "".
    address: str = ""


def from_openapi(document: Mapping[str, Any]) -> Imported:
    """One OpenAPI 3 description as tool files, named shapes and the report."""
    version = str(document.get("openapi") or "")
    if not version.startswith("3."):
        said = f"Swagger {document['swagger']}" if "swagger" in document else "no `openapi: 3.x` line"
        raise NotImported(
            f"this is {said}, and only OpenAPI 3 descriptions are read. Fix: convert it to OpenAPI 3 "
            "(the Swagger Editor's *Convert to OpenAPI 3* does it), then import that."
        )
    info = document.get("info") if isinstance(document.get("info"), Mapping) else {}
    title = str(info.get("title") or "api")
    api = kebab(title)[:40].strip("-") or "api"
    named = " ".join(str(x) for x in (title, info.get("version")) if x)
    report = ImportReport(kind=f"an OpenAPI description ({named})")
    shapes = Shapes(document, report, api)
    made = Operations(document, shapes, api, title)
    for key in document:
        bucket, what = TOP.get(key, ("unmapped", f"`{key}`, which this importer does not read"))
        getattr(shapes, bucket)(key, what)
    made.schemes()
    paths = document.get("paths") if isinstance(document.get("paths"), Mapping) else {}
    for path, item in paths.items():
        made.path(str(path), item)
    servers = document.get("servers") or [{}]
    address = str(servers[0].get("url") or "") if isinstance(servers[0], Mapping) else ""
    owed = [
        f"bind `{api}` to the API's address ({address or 'the description names none'}) on the host that "
        "runs these tools"
    ]
    owed += made.credentials + made.owed
    report.still_to_write = tuple(owed)
    report.seen = tuple(shapes.seen)
    used = _reached(shapes.named, made.lines)
    return Imported(
        api=api,
        files=made.files,
        shapes={k: v for k, v in shapes.named.items() if k in used},
        report=report,
        needs_a_look=tuple(made.needs_a_look),
        address=address,
    )


def _reached(named: Mapping[str, Mapping[str, str]], lines: list[str]) -> set[str]:
    """The named shapes these lines use, and the shapes those use, and so on."""
    found: set[str] = set()
    todo = list(lines)
    while todo:
        line = todo.pop().removesuffix(", optional")
        while line.startswith("list of "):
            line = line[len("list of "):]
        if line in named and line not in found:
            found.add(line)
            todo += list(named[line].values())
    return found


def write_into(root: Path, imported: Imported) -> list[str]:
    """Write the tool files into the tree at `root`, and their named shapes into its
    `workspace.yaml`. A file already there with other words, or a shape already there
    with other parts, is refused before anything is written; one with the same words is
    left as it is, so importing twice writes nothing the second time."""
    workspace = root / "workspace.yaml"
    if not workspace.is_file():
        raise NotImported(f"{root} holds no workspace.yaml. Fix: import into a PACT tree, or make one there first.")
    try:
        clash = [f for f, body in imported.files.items() if (root / f).exists() and (root / f).read_bytes() != _bytes(body)]
        text = workspace.read_text()
        found = yaml.safe_load(text) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as trouble:
        raise NotImported(
            f"{root} could not be read as a PACT tree ({' '.join(str(trouble).split())}). Nothing was written. "
            "Fix: make workspace.yaml and tools/ readable YAML (`pact check` says where), then import again."
        ) from None
    have = found.get("shapes") if isinstance(found, Mapping) else None
    have = have if isinstance(have, Mapping) else {}
    clash += [f"workspace.yaml shapes: {n}" for n, parts in imported.shapes.items() if n in have and have[n] != parts]
    if clash:
        raise NotImported(
            f"these are already in {root} and say something else: {', '.join(clash)}. Nothing was written. "
            "Fix: import into another tree, or delete them first if the import should replace them."
        )
    new = {n: parts for n, parts in imported.shapes.items() if n not in have}
    written: list[str] = []
    try:
        if new:
            workspace.write_text(_with_shapes(text, new))
            written.append("workspace.yaml")
        for f, body in imported.files.items():
            path = root / f
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_bytes(body))
            written.append(f)
    except OSError as trouble:
        raise NotImported(
            f"{root} could not be written ({trouble.strerror or trouble}); written before that: "
            f"{', '.join(written) or 'nothing'}. Fix: make the tree writable, then import again (what is "
            "there already is left as it is)."
        ) from None
    return written


def _bytes(body: str | bytes) -> bytes:
    return body if isinstance(body, bytes) else body.encode("utf-8")


def _with_shapes(text: str, new: Mapping[str, Mapping[str, str]]) -> str:
    """`workspace.yaml`'s words with `new` added under `shapes:`, every other line as written."""
    block = yaml.safe_dump(dict(new), sort_keys=False, allow_unicode=True, width=100)
    lines = text.splitlines(keepends=True)
    at = next((i for i, line in enumerate(lines) if re.match(r"shapes\s*:", line)), None)
    if at is None:
        indented = "".join(f"  {line}" for line in block.splitlines(keepends=True))
        return text + ("" if text.endswith("\n") else "\n") + "\nshapes:\n" + indented
    if not re.fullmatch(r"shapes\s*:\s*(#.*)?\n?", lines[at]):
        raise NotImported(
            "workspace.yaml writes `shapes:` on one line, and the imported shapes go under it. Fix: write "
            "`shapes:` as a block, one shape per line beneath it, then import again."
        )
    after = next((line for line in lines[at + 1:] if line.strip() and not line.lstrip().startswith("#")), "  ")
    pad = " " * (len(after) - len(after.lstrip())) or "  "
    indented = "".join(f"{pad}{line}" for line in block.splitlines(keepends=True))
    return "".join(lines[: at + 1]) + indented + "".join(lines[at + 1:])
