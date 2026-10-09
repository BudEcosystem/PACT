"""Every example a `moment` field's help shows loads.

`pact_reference` serves the schema's help to models, and the reference pages
print it, so an example there is a line somebody will type. `workflow.kept-for`
once showed `{at: input.matter-closed-on, after: 7 years}`, which the loader
refuses (a duration has no years). The examples are found, not listed: every
field typed `moment`, every backticked value in its help that is one. All of
them are one type, so each is loaded on one moment line, `kept-for:` on
something an agent remembers, and the loader must have nothing to say about it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trees import REPO, pact, write  # noqa: E402

SCHEMA = yaml.safe_load((REPO / "spec/schema.yaml").read_text())


def _examples() -> list[tuple[str, str]]:
    found = []
    for group, body in SCHEMA["groups"].items():
        for field, spec in (body.get("fields") or {}).items():
            if not isinstance(spec, dict) or spec.get("type") != "moment":
                continue
            for written in re.findall(r"`([^`]+)`", " ".join(str(spec.get("help", "")).split())):
                if written.startswith("{") or re.match(r"\d", written):
                    found.append((f"{group}.{field}", written))
    return found


EXAMPLES = _examples()


def test_the_help_shows_moments_to_check() -> None:
    fields = {f for f, _ in EXAMPLES}
    assert {"workflow.kept-for", "ownership.locked-until"} <= fields, EXAMPLES


@pytest.mark.parametrize(("field", "written"), EXAMPLES, ids=[f"{f}={w}" for f, w in EXAMPLES])
def test_a_moment_the_help_shows_loads(tmp_path: Path, field: str, written: str) -> None:
    root = write(
        tmp_path,
        {
            "workspace.yaml": "name: moments\nallow-egress: []\n",
            "agents/keeper.yaml": (
                "description: Keeps one thing.\ninstructions: Help.\nremembers:\n  note:\n"
                f"    description: a note\n    lasts: forever\n    kept-for: {written}\n"
            ),
        },
    )
    out = pact("check", str(root))
    assert "kept-for" not in out.stdout and out.returncode == 0, f"{field} shows `{written}`:\n{out.stdout}"
