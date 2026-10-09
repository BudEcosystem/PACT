"""Where the `pact` loader binary is, found one way for every caller.

Every command here that reads a workspace shells out to the Rust loader, and
each used to build its own path to `target/debug/pact` inside the checkout. That
path exists only in a source checkout with a debug build, so an installed
package (no checkout) or a release build (no debug folder) reported "the loader
is not built" while a perfectly good `pact` sat on the PATH.

One search order, written once:

1. `PACT_BIN` — the host said exactly which binary; nothing else is consulted,
   so a typo there is reported rather than papered over by a different build.
2. `<checkout>/target/release/pact` or `<checkout>/target/debug/pact`, when this
   module runs from a PACT checkout — the build of the very source beside it,
   whichever of the two was built LAST. Release used to win outright, and the
   gate (`scripts/test-all.sh`, every test that reads through the loader) builds
   and tests debug: so after a change to the loader a stale release binary went
   on answering for everything that found it this way, with the fixed one
   sitting beside it. It comes before anything installed for the same reason: a
   development environment also has the `pact-loader` wheel installed, built
   from the checkout as it was when the environment was last synced.
3. `pact` in this interpreter's scripts folder (`<venv>/bin/pact`) — where the
   `pact-loader` wheel, which `pact-adapters` depends on at its own version,
   installs it. Found whether or not that folder is on the `PATH`, so a host that
   runs `/srv/venv/bin/python` without activating the environment finds it too.
4. `pact` on the `PATH` — a loader installed some other way.
"""

from __future__ import annotations

import os
import shutil
import sysconfig
from collections.abc import Mapping
from pathlib import Path

#: The PACT checkout this module sits in, when it sits in one
#: (`<repo>/adapters/python/src/pact_adapters/loader.py`).
REPO = Path(__file__).resolve().parents[4]

#: This interpreter's scripts folder, where an installed `pact-loader` wheel put `pact`.
INSTALLED = Path(sysconfig.get_path("scripts"))

#: The environment variable that names the binary outright.
ENV = "PACT_BIN"

#: What to type when nothing is found, quoted by every caller's message.
FIX = (
    "install it with `pip install pact-loader` (`pact-adapters` depends on it), set "
    "PACT_BIN to the `pact` binary, put `pact` on your PATH, or build it in the PACT "
    "checkout with `cargo build --release -p pact-cli`"
)


def shipped(*parts: str) -> Path:
    """A file of the PACT checkout that travels with the package: `shipped("spec",
    "schema.yaml")`, `shipped("models", "catalog.yaml")`.

    A wheel carries each inside the package (`pact_adapters/<parts>`, `pyproject.toml`'s
    `force-include`), because an installed package sits in no checkout: it used to resolve no
    shipped model and find no schema. A source checkout reads the checkout's own file, so an
    edit there is seen at once.
    """
    carried = Path(__file__).resolve().parent.joinpath(*parts)
    return carried if carried.is_file() else REPO.joinpath(*parts)


def schema_path() -> Path:
    """PACT's specification, `spec/schema.yaml`: the one description of every kind and field."""
    return shipped("spec", "schema.yaml")


def pact_binary(
    *,
    environ: Mapping[str, str] | None = None,
    repo: Path | None = None,
    installed: Path | None = None,
) -> Path | None:
    """The `pact` binary to run, or `None` when there is none to be found.

    `environ`, `repo` and `installed` exist for tests; callers pass nothing.
    """
    env = os.environ if environ is None else environ
    named = env.get(ENV, "").strip()
    if named:
        path = Path(named).expanduser()
        return path if path.is_file() else None
    root = REPO if repo is None else repo
    built = [b for b in (root / "target" / kind / "pact" for kind in ("release", "debug")) if b.is_file()]
    if built:
        # The newest build; release when the two are the same age.
        return max(built, key=lambda b: b.stat().st_mtime_ns)
    beside = (INSTALLED if installed is None else installed) / "pact"
    if beside.is_file() and os.access(beside, os.X_OK):
        return beside
    on_path = shutil.which("pact", path=env.get("PATH"))
    return Path(on_path) if on_path else None
