"""Where a mistake is, in one shape, for whichever module found it.

For a round there were two shapes. `context_policy.Problem` carried a file and a
line and searched the tree for the phrase that was wrong; every interceptor
diagnostic wrote ``f"interceptors/{name}.yaml"`` — a path **synthesised from the
entry's name rather than found**. In the folder-of-folders spelling the loader
accepts, an interceptor lives at `interceptors/stop-runaway-refunds/
interceptor.yaml`, so the synthesised path named a file that does not exist on
disk, at no line at all. The author was sent somewhere they could not open.

One shape and one search, imported by both. The rule is the project's own and it
has no exceptions: every diagnostic names the file, the line, what is wrong, and
something the author can type.

The search exists because the loaded document carries no spans. An adapter sees
`pact show` output (invariant P-1), which is settings without positions, so the
line is recovered by looking the author's own phrase up in the file the Expansion
Rule says it came from. When that file is not on disk — a rule written inline in
`workspace.yaml`, or a document handed over without its tree — the file is still
named and the line is 1, because a diagnostic that names no file is not one an
author can act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: What a folder-shaped document may call its own settings file, in the order
#: they are looked for. Mirrors `Policy::is_self_file` in `pact-loader`: a file
#: named after WHAT IT IS (`interceptor.yaml`), the explicit `_index.yaml`, or a
#: file named after the folder. Kept in step with that function rather than
#: guessed at — a candidate list that has drifted sends an author to the wrong
#: file, which is the failure this module exists to remove.
SELF_FILES: tuple[str, ...] = ("{kind}", "_index", "{name}")

#: Extensions the loader reads. `.yml` is here because authors type it and being
#: strict about it would teach nothing.
SUFFIXES: tuple[str, ...] = (".yaml", ".yml")


@dataclass(frozen=True)
class Problem:
    """A problem in the four-part form `pact-diag` requires: where, what, why,
    how. Rendered to match the Rust renderer exactly, so an author meets one
    format whichever half of the system found the mistake."""

    rule: str
    file: str
    line: int
    message: str
    fix: str
    severity: str = "warning"

    def __str__(self) -> str:
        return (
            f"{self.severity}: {self.message}\n"
            f"  --> {self.file}:{self.line}:1\n"
            f"  fix: {self.fix}\n"
            f"  rule: {self.rule}\n"
        )


def locate(
    source: "Path | None", folder: str, kind: str, name: str, needle: str
) -> tuple[str, int]:
    """Find the file and line a phrase was written on.

    `folder` is the plural directory (`interceptors`), `kind` the singular the
    loader accepts as a self file (`interceptor`), `name` the entry, and `needle`
    a phrase from the author's own words. Every spelling the Expansion Rule
    allows is tried, so a rule written as a folder is found exactly as one
    written as a file.
    """
    for path in _candidates(source, folder, kind, name):
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        if needle:
            # A setting the author wrote beats a comment ABOUT that setting. The
            # worked example's `metrics:` block is introduced by a comment naming
            # `deepeval:answer_relevancy`, and pointing somebody at the sentence
            # explaining a score rather than at the score sends them to edit
            # prose. Comments are still matched on the second pass, because a
            # phrase that appears nowhere else is better located there than not
            # at all.
            for wanted in (False, True):
                for i, line in enumerate(lines, start=1):
                    if line.lstrip().startswith("#") is not wanted:
                        continue
                    if needle in line:
                        return _shown(path, source), i
        # The file is real and the phrase is not on one line of it — a folded
        # scalar, most often, which is how every long rule in the worked example
        # is written. Naming the file at line 1 beats naming a file that does
        # not exist at all.
        return _shown(path, source), 1
    return f"{folder}/{name}.yaml", 1


def _candidates(
    source: "Path | None", folder: str, kind: str, name: str
) -> "list[Path]":
    if source is None:
        return []
    out: list[Path] = []
    for suffix in SUFFIXES:
        out.append(source / folder / f"{name}{suffix}")
        for spelling in SELF_FILES:
            stem = spelling.format(kind=kind, name=name)
            out.append(source / folder / name / f"{stem}{suffix}")
        out.append(source / f"workspace{suffix}")
    return out


def _shown(path: "Path", source: "Path | None") -> str:
    """The path as the author would type it — relative to their workspace."""
    if source is None:
        return str(path)
    try:
        return str(path.relative_to(source))
    except ValueError:
        return str(path)
