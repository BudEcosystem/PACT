"""A dependency the source imports and the manifest does not name (Phase 3, bug 7).

`ollama_transport.py` and `judge.py` both `import httpx`, and `pyproject.toml`
did not list it. It resolved anyway — something else in the tree pulls it — which
is the whole problem: **it works until the next re-lock**, and then the transport
that talks to a locally-served model stops importing on a box with no network to
fix it from. That is the air-gapped case, which is the case PACT is for.

`scripts/pact-eval` makes it worse than a latent break. It PROBES
`python3 -c "import httpx, yaml"` to decide whether a bare interpreter can be
used at all, so the one fallback path the wrapper has was gated on a package
nothing declared.

The check is deliberately narrow: only top-level `import x` / `from x import` of
names that are not this package, not the standard library, and not a test-only
import. It is looking for the specific drift above, not auditing packaging.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "adapters" / "python"
SRC = ADAPTER / "src" / "pact_adapters"
MANIFEST = ADAPTER / "pyproject.toml"

#: Distribution name for an import name that differs from it. Only the ones this
#: tree actually uses — a general mapping would be a package index, and wrong.
DISTRIBUTION: dict[str, str] = {
    "yaml": "pyyaml",
    "autogen_agentchat": "autogen-agentchat",
    "autogen_core": "autogen-core",
    "langchain_core": "langchain-core",
    "agents": "openai-agents",
    "pydantic_ai": "pydantic-ai-slim",
}

#: Imports that are guarded by a `try:` or sit inside a function precisely
#: BECAUSE they may be absent, and whose absence is already reported to the author
#: rather than crashing. Each is a decision, not an omission.
OPTIONAL: frozenset[str] = frozenset({
    # Every framework transport imports its own SDK lazily, so a workspace that
    # uses one target does not have to install the other six. `test_portability`
    # skips a target whose SDK is missing rather than failing.
    "deepeval",
})


def _imported() -> dict[str, set[str]]:
    """`{top-level module: {files that import it}}` across the adapter source."""
    found: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(errors="ignore"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                found.setdefault(name, set()).add(str(path.relative_to(ADAPTER)))
    return found


def _declared() -> set[str]:
    """Every distribution named in `[project] dependencies`."""
    import re

    text = MANIFEST.read_text()
    block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    return {
        re.split(r"[<>=!~\[]", line.strip().strip('",'), 1)[0].strip().lower()
        for line in block.splitlines()
        if line.strip().startswith('"')
    }


def test_the_manifest_parses_into_something() -> None:
    """Without this the two tests below pass vacuously on an empty set."""
    declared = _declared()
    assert len(declared) > 5, f"the dependency block did not parse: {declared}"
    assert "pyyaml" in declared


def test_every_third_party_import_is_a_declared_dependency() -> None:
    """The check `httpx` failed.

    An import that resolves transitively is not a declared dependency; it is a
    dependency that works until somebody re-locks. `resolve.py`'s own comment
    beside `pyyaml` already said this in words — *"a dependency the source uses
    but the manifest does not name is one that disappears on the next re-lock"* —
    and `httpx` sat two files away, undeclared, saying nothing.
    """
    declared = _declared()
    stdlib = set(sys.stdlib_module_names)
    missing: dict[str, set[str]] = {}
    for name, where in _imported().items():
        if name in stdlib or name in OPTIONAL or name in {"pact_adapters", ""}:
            continue
        if name.startswith("_") or (SRC / f"{name}.py").exists():
            continue          # a sibling module of this package
        if DISTRIBUTION.get(name, name).lower() not in declared:
            missing[name] = where
    assert not missing, (
        "imported by the adapter and named nowhere in `pyproject.toml`:\n"
        + "\n".join(f"  {n} — {', '.join(sorted(w))}" for n, w in sorted(missing.items()))
        + "\nAdd each to `[project] dependencies`, or to OPTIONAL here with the "
        "reason its absence is already reported to the author."
    )


def test_what_the_wrapper_probes_for_is_declared() -> None:
    """`scripts/pact-eval` decides whether a bare `python3` can run the adapter by
    probing for these. A probe for a package the manifest does not name is a
    fallback path that works by luck."""
    wrapper = (REPO / "scripts" / "pact-eval").read_text()
    line = next(
        (ln for ln in wrapper.splitlines() if "python3 -c" in ln and "import" in ln),
        "",
    )
    assert line, "the wrapper's interpreter probe is gone — has the fallback changed?"
    probed = {
        n.strip().rstrip('"').strip()
        for n in line.split("import", 1)[1].split('"')[0].split(",")
        if n.strip()
    }
    assert probed, f"could not read what is probed for: {line!r}"
    declared = _declared()
    undeclared = sorted(
        n for n in probed if DISTRIBUTION.get(n, n).lower() not in declared
    )
    assert not undeclared, (
        f"`scripts/pact-eval` probes for {undeclared}, which `pyproject.toml` "
        f"does not name — so the interpreter it falls back to is gated on a "
        f"package nothing installs on purpose."
    )
