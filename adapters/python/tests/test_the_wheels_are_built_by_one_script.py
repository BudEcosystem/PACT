"""What PACT publishes is built by one script, which CI runs as it is, and published only on
the owner's approval with no token stored anywhere.

`scripts/build-wheels.sh` builds `pact-loader` (the `pact` binary as a wheel), its source
distribution and the `pact-adapters` wheel, checks them and installs them; `wheels.yml` runs it
on each architecture. The same rule as the gate (`test_the_gate_is_run_by_something.py`): a
workflow that spelled the build out would be a second copy of it, and the two would drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "build-wheels.sh"
WORKFLOW = REPO / ".github" / "workflows" / "wheels.yml"


def _workflow() -> dict:
    # PyYAML reads the bare key `on` as True.
    said = yaml.safe_load(WORKFLOW.read_text())
    said["on"] = said.pop(True, said.get("on"))
    return said


def test_the_workflow_runs_the_script_rather_than_a_copy_of_it() -> None:
    steps = _workflow()["jobs"]["build"]["steps"]
    runs = [s["run"] for s in steps if "run" in s]
    assert "./scripts/build-wheels.sh" in runs, runs
    for copied in ("maturin", "uv build", "twine", "pip install"):
        assert not any(copied in r for r in runs), f"the workflow runs `{copied}` itself"


def test_both_architectures_are_built_and_installed_on_their_own_runners() -> None:
    runners = {m["runner"] for m in _workflow()["jobs"]["build"]["strategy"]["matrix"]["include"]}
    assert runners == {"ubuntu-latest", "ubuntu-24.04-arm"}, runners


def test_publishing_needs_a_tag_the_owner_s_approval_and_no_stored_token() -> None:
    said = _workflow()
    publish = said["jobs"]["publish"]
    assert publish["needs"] == "build"
    assert publish["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert publish["environment"] == "pypi", "the environment whose required reviewer is the owner"
    assert publish["permissions"] == {"id-token": "write"}, "trusted publishing, nothing else"
    assert said["permissions"] == {"contents": "read"}
    text = WORKFLOW.read_text()
    assert "secrets." not in text and "password" not in text, "a stored token is back"
    assert any(s.get("uses", "").startswith("pypa/gh-action-pypi-publish@") for s in publish["steps"])


def test_the_script_proves_the_installed_wheels_and_a_build_from_the_source() -> None:
    said = SCRIPT.read_text()
    assert "--zig" in said and "--release" in said, "the binary must ask for no glibc newer than 2.28"
    assert "twine check --strict" in said
    assert re.search(r"uv build .*--wheel .*pact_loader-.*\.tar\.gz", said), "the sdist alone is never built"
    assert "env -u PACT_BIN PATH=/usr/bin:/bin" in said, "the installed loader must be found off the PATH"
    assert 'check refund-desk' in said
    assert 'GITHUB_REF_NAME' in said, "a tag that is not the version must stop the release"


def test_the_loader_wheel_is_linux_manylinux_2_28_and_carries_what_it_compiles_in() -> None:
    import tomllib

    maturin = tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["maturin"]
    assert maturin["compatibility"] == "manylinux_2_28"
    carried = {i["path"] for i in maturin["include"]}
    compiled_in = set()
    for source in (REPO / "crates").rglob("*.rs"):
        for path in re.findall(r'include_str!\("((?:\.\./)+)([^"]+)"\)', source.read_text()):
            resolved = (source.parent / (path[0] + path[1])).resolve()
            if not resolved.is_relative_to(source.parents[1]):  # outside its own crate
                compiled_in.add(resolved.relative_to(REPO).parts[0])
    assert compiled_in, "the scan found nothing: it is reading the wrong files"
    for top in compiled_in:
        assert any(c == top or c.startswith(f"{top}/") for c in carried), (
            f"`{top}/` is compiled into the binary and the source distribution does not carry it"
        )
