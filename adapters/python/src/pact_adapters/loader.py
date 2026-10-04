"""Where the `pact` loader binary is, found one way for every caller.

Every command here that reads a workspace shells out to the Rust loader, and
each used to build its own path to `target/debug/pact` inside the checkout. That
path exists only in a source checkout with a debug build, so an installed
package (no checkout) or a release build (no debug folder) reported "the loader
is not built" while a perfectly good `pact` sat on the PATH.

One search order, written once:

1. `PACT_BIN` — the host said exactly which binary; nothing else is consulted,
   so a typo there is reported rather than papered over by a different build.
2. `pact` on the `PATH` — an installed loader.
3. `<checkout>/target/release/pact`, then `<checkout>/target/debug/pact` — a
   source checkout, release first because it is the build a person makes to use
   rather than to debug.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

#: The PACT checkout this module sits in, when it sits in one
#: (`<repo>/adapters/python/src/pact_adapters/loader.py`).
REPO = Path(__file__).resolve().parents[4]

#: The environment variable that names the binary outright.
ENV = "PACT_BIN"

#: What to type when nothing is found, quoted by every caller's message.
FIX = (
    "set PACT_BIN to the `pact` binary, put `pact` on your PATH, or build it in "
    "the PACT checkout with `cargo build --release -p pact-cli`"
)


def pact_binary(
    *, environ: Mapping[str, str] | None = None, repo: Path | None = None
) -> Path | None:
    """The `pact` binary to run, or `None` when there is none to be found.

    `environ` and `repo` exist for tests; callers pass nothing.
    """
    env = os.environ if environ is None else environ
    named = env.get(ENV, "").strip()
    if named:
        path = Path(named).expanduser()
        return path if path.is_file() else None
    on_path = shutil.which("pact", path=env.get("PATH"))
    if on_path:
        return Path(on_path)
    root = REPO if repo is None else repo
    for build in ("release", "debug"):
        candidate = root / "target" / build / "pact"
        if candidate.is_file():
            return candidate
    return None
