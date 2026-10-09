"""The core installs with three Python packages and the loader, and imports with only them.

`pact-adapters` core is `pydantic-ai-slim`, `pyyaml` and `httpx`, and `pact-loader`, the wheel
that carries the `pact` binary (no Python code) at exactly this package's version. Everything
else — the five other frameworks' SDKs, the eval metrics, the test runner — is an
optional extra named by the transport that binds it. A host running PACT on
Pydantic AI (Bud Flow) installs the core and must be able to import every module
it might reach without LangGraph, AutoGen or DeepEval on the machine.

Held by importing every core module in a fresh interpreter whose import system
refuses the heavy packages (a `sys.meta_path` finder), so a heavy import that
creeps into a core module fails here, at its module, instead of in somebody's
install. The five framework transports are the only modules allowed to need an
extra, and each is checked to still need it — a transport that stopped needing
one belongs in the core.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[1]
SRC = ADAPTER / "src"
MANIFEST = ADAPTER / "pyproject.toml"

#: Import names that only an extra installs.
HEAVY = (
    "anthropic", "autogen_agentchat", "autogen_core", "autogen_ext", "langgraph",
    "langchain_core", "langchain", "agents", "openai", "deepeval", "pytest",
)

#: The modules allowed to need an extra, and the extra that installs it.
NEEDS_AN_EXTRA: dict[str, str] = {
    "pact_adapters.transports.anthropic_transport": "anthropic",
    "pact_adapters.transports.autogen_transport": "autogen",
    "pact_adapters.transports.langgraph_transport": "langgraph",
    "pact_adapters.transports.langchain_transport": "langchain",
    "pact_adapters.transports.openai_agents_transport": "openai-agents",
}

#: Runs in a fresh interpreter: blocks HEAVY, imports every module, reports
#: which failed and why, as JSON on stdout.
_PROBE = """
import importlib, importlib.abc, json, sys
HEAVY = set(sys.argv[1].split(","))
class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in HEAVY:
            raise ImportError(f"{name} is only in an extra", name=name)
        return None
sys.meta_path.insert(0, Refuse())
sys.path.insert(0, sys.argv[2])
from pathlib import Path
# By file, not by `pkgutil`: `transports/` and `mcp/` are namespace packages
# (no `__init__.py`), which `walk_packages` never descends into.
root = Path(sys.argv[2])
names = sorted(
    ".".join(p.relative_to(root).with_suffix("").parts)
    for p in (root / "pact_adapters").rglob("*.py")
)
failed = {}
for name in names:
    try:
        importlib.import_module(name)
    except Exception as e:
        failed[name] = f"{type(e).__name__}: {e}"
print(json.dumps({"seen": names, "failed": failed}))
"""


def _failed_without_extras() -> dict[str, str]:
    done = subprocess.run(
        [sys.executable, "-c", _PROBE, ",".join(HEAVY), str(SRC)],
        capture_output=True, text=True, timeout=300,
    )
    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout)
    # A probe that saw nothing passes everything: hold it to the tree it walked.
    assert len(said["seen"]) > 40 and set(NEEDS_AN_EXTRA) <= set(said["seen"]), said["seen"]
    return said["failed"]


def test_every_core_module_imports_without_any_extra() -> None:
    failed = _failed_without_extras()
    core = {m: why for m, why in failed.items() if m not in NEEDS_AN_EXTRA}
    assert not core, (
        "core modules that need a package only an extra installs:\n"
        + "\n".join(f"  {m}: {why}" for m, why in sorted(core.items()))
        + "\n  fix: import it inside the function that needs it, or move the module "
        "behind an extra in NEEDS_AN_EXTRA with the extra that installs it."
    )
    still = sorted(set(NEEDS_AN_EXTRA) - set(failed))
    assert not still, f"{still} import without their extra: they belong in the core"


def test_the_core_is_three_packages_and_the_loader_and_each_extra_exists() -> None:
    project = tomllib.loads(MANIFEST.read_text())["project"]
    core = {d.split(">")[0].split("=")[0].split("<")[0].strip() for d in project["dependencies"]}
    assert core == {"pydantic-ai-slim", "pyyaml", "httpx", "pact-loader"}, core
    extras = project["optional-dependencies"]
    for module, extra in NEEDS_AN_EXTRA.items():
        assert extra in extras, f"{module} names the extra {extra!r}, which does not exist"
    assert {"all", "test"} <= set(extras)
    every = ",".join(sorted(set(extras) - {"all", "test"}))
    assert extras["all"] == [f"pact-adapters[{every}]"] or set(
        extras["all"][0].split("[", 1)[1].rstrip("]").split(",")
    ) == set(every.split(",")), extras["all"]
    assert any(d.startswith("pytest") for d in extras["test"])


def test_the_report_names_the_extra_when_it_reaches_for_a_missing_framework() -> None:
    """`conformance` imports without the frameworks; building one says what to install."""
    probe = _PROBE.split("from pathlib import Path", 1)[0] + (
        "from pact_adapters import conformance\n"
        "try:\n"
        "    conformance.TARGETS['langgraph'](None)\n"
        "except ImportError as e:\n"
        "    print(json.dumps(str(e)))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe, ",".join(HEAVY), str(SRC)],
        capture_output=True, text=True, timeout=300,
    )
    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout)
    assert "LangGraphTransport" in said and "pact-adapters[all]" in said, said


def test_the_loader_is_pinned_at_the_version_both_are_released_at() -> None:
    """`pact-adapters` reads the document `pact` writes, so it depends on exactly the loader of
    its own version, and both are the Cargo workspace's version: one number to move per release.
    A pin left behind would install last release's loader under this release's adapters."""
    repo = ADAPTER.parents[1]
    project = tomllib.loads(MANIFEST.read_text())["project"]
    workspace = tomllib.loads((repo / "Cargo.toml").read_text())["workspace"]["package"]["version"]
    assert project["version"] == workspace, (project["version"], workspace)
    assert f"pact-loader=={workspace}" in project["dependencies"], project["dependencies"]
    loader = tomllib.loads((repo / "pyproject.toml").read_text())
    assert loader["project"]["name"] == "pact-loader"
    assert loader["project"]["dynamic"] == ["version"], "the wheel's version is the crate's, never typed twice"
    assert loader["tool"]["maturin"]["bindings"] == "bin"
    assert loader["tool"]["maturin"]["manifest-path"] == "crates/pact-cli/Cargo.toml"
    assert tomllib.loads((ADAPTER / "pyproject.toml").read_text())["tool"]["uv"]["sources"]["pact-loader"] == {
        "path": "../.."
    }
