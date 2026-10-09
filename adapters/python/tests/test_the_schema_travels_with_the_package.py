"""The specification is found from an installed package as well as from a checkout.

`spec/schema.yaml` lives at the top of the PACT checkout, which a wheel does not carry: a host
that installed `pact-adapters` and asked what fields an agent has got a path that did not exist.
The wheel now carries the file inside the package, and `loader.schema_path()` is the one place
that knows both homes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ADAPTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADAPTER / "src"))

from pact_adapters import loader  # noqa: E402


def test_a_checkout_reads_its_own_specification() -> None:
    found = loader.schema_path()
    assert found == loader.REPO / "spec" / "schema.yaml"
    assert "agent" in yaml.safe_load(found.read_text(encoding="utf-8"))["groups"]


def test_the_wheel_carries_each_file_where_the_package_looks_for_it(tmp_path: Path, monkeypatch) -> None:
    carried = tomllib.loads((ADAPTER / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"][
        "build"
    ]["targets"]["wheel"]["force-include"]
    assert set(carried.values()) == {"pact_adapters/spec/schema.yaml", "pact_adapters/models/catalog.yaml"}
    # An installed package: the module sits in site-packages and each file sits beside it.
    package = tmp_path / "site-packages" / "pact_adapters"
    monkeypatch.setattr(loader, "__file__", str(package / "loader.py"))
    for source, target in carried.items():
        parts = Path(target).parts[1:]
        assert (ADAPTER / source).resolve() == loader.REPO.joinpath(*parts)
        shipped = tmp_path / "site-packages" / target
        shipped.parent.mkdir(parents=True)
        shipped.write_text("groups: {}\n", encoding="utf-8")
        assert loader.shipped(*parts) == shipped
    assert loader.schema_path() == package / "spec" / "schema.yaml"


def test_the_built_wheel_installed_alone_resolves_a_shipped_model_and_finds_the_schema(
    tmp_path: Path,
) -> None:
    """The real thing, not its description: build the wheel, install it in a clean
    environment, and ask from a directory that is in no checkout.

    Before the two files travelled, this printed an empty catalogue with
    `catalog/missing` and a schema path that did not exist: `BUILTIN_CATALOGUE`
    and `REPO` both pointed four folders above `site-packages`.
    """
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is what builds and installs the wheel here")

    def do(*args: str, cwd: Path = ADAPTER) -> str:
        done = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr
        return done.stdout

    do(uv, "build", "--wheel", "--offline", "--out-dir", str(tmp_path / "dist"), ".")
    # And the loader's wheel, which the adapters depend on at their own version (maturin builds
    # `pact` from the Rust at the repository root).
    do(uv, "build", "--wheel", "--offline", "--out-dir", str(tmp_path / "dist"), str(ADAPTER.parents[1]))
    wheels = sorted(str(w) for w in (tmp_path / "dist").glob("*.whl"))
    assert len(wheels) == 2, wheels
    venv = tmp_path / "venv"
    do(uv, "venv", "--offline", "-q", str(venv))
    python = str(venv / "bin" / "python")
    do(uv, "pip", "install", "--offline", "-q", "--python", python, *wheels)
    asked = (
        "import json; from pact_adapters import loader, resolve\n"
        "c = resolve.load_catalogue()\n"
        "print(json.dumps({'default': resolve.default_model(), 'rows': len(c.entries),\n"
        "  'problems': [p.rule for p in c.problems], 'schema': loader.schema_path().is_file(),\n"
        "  'from': str(resolve.BUILTIN_CATALOGUE), 'pact': str(loader.pact_binary())}))\n"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    said = json.loads(do(python, "-c", asked, cwd=elsewhere))
    assert str(venv) in said["from"], f"it read a checkout, not the wheel: {said['from']}"
    assert said["rows"] > 0 and said["problems"] == [], said
    assert said["default"], "the shipped catalogue names a default model and none was resolved"
    assert said["schema"] is True
    assert said["pact"] == str(venv / "bin" / "pact"), f"the loader found is not the wheel's: {said['pact']}"
