"""Every number the documentation site quotes is one this repository has.

Documentation drifts. This repository has already shipped a README quoting a
test count it did not have, an architecture claiming a kind cost "no Rust
change" when a load-bearing one was made, and an inventory whose own stated
totals disagreed with its rows — each caught by a test, none by a reader.

The site is the surface a newcomer trusts most and checks least, so its numbers
are held the same way: recomputed here, and the failure message says exactly what
to write.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site-docs"


def site_text() -> str:
    return "\n".join(p.read_text() for p in sorted(SITE.rglob("*.md")))


# ────────────────────────────────────────────────────── the format's own shape


def test_the_kind_count_is_the_number_of_kinds() -> None:
    kinds = len(yaml.safe_load((REPO / "spec/schema.yaml").read_text())["groups"])
    text = site_text()
    # Three spellings the site actually uses. The first version of this test
    # matched only the prose form and passed happily while a table row said 41 —
    # a test that agrees with a wrong document is worse than no test.
    quoted = {int(n) for n in re.findall(r"\*\*(\d+) kinds\*\*", text)}
    quoted |= {int(n) for n in re.findall(r"The (\d+) kinds", text)}
    quoted |= {int(n) for n in re.findall(r"\|\s*Schema kinds\s*\|\s*\*\*(\d+)\*\*", text)}
    assert quoted, "the site should say how many kinds there are"
    assert quoted == {kinds}, (
        f"the site quotes {sorted(quoted)} kinds and spec/schema.yaml has {kinds}. "
        f"`reference/kinds.md` is generated — regenerate it and fix any prose."
    )


def test_the_named_field_count_is_the_number_of_fields_that_resolve_a_name() -> None:
    real = len(re.findall(r"^\s*names:", (REPO / "spec/schema.yaml").read_text(), re.M))
    quoted = {int(n) for n in re.findall(r"\*\*(\d+) fields\*\* declare what they name", site_text())}
    quoted |= {int(n) for n in re.findall(r"Fields that resolve a name \| \*\*(\d+)\*\*", site_text())}
    assert quoted == {real}, (
        f"the site quotes {sorted(quoted)} and `grep -cE '^\\s*names:' spec/schema.yaml` "
        f"gives {real}"
    )


def test_the_worked_example_file_count_excludes_the_runtime_directory() -> None:
    """`.pact/` is derived output, gitignored, and deleting it must be harmless.
    Counting it would make the "no code in it" claim rest on a moving number."""
    authored = [
        p for p in (REPO / "examples/refund-desk").rglob("*")
        if p.is_file() and ".pact" not in p.parts
    ]
    quoted = {int(n) for n in re.findall(r"(\d+) authored files", site_text())}
    quoted |= {int(n) for n in re.findall(r"^(\d+) files: a supervisor", site_text(), re.M)}
    assert quoted == {len(authored)}, (
        f"the site quotes {sorted(quoted)} and the example has {len(authored)} authored files"
    )


# ─────────────────────────────────────────────────────────── the CLI's own words


def test_every_verb_the_site_documents_is_a_verb_the_binary_has() -> None:
    """The worked example instructed five commands the binary did not have, for a
    round. A site that teaches a command nobody can run is worse than one that
    omits it."""
    binary = REPO / "target/debug/pact"
    if not binary.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    helped = subprocess.run([str(binary), "help"], capture_output=True, text=True).stdout
    documented = set(re.findall(r"^`pact (\w+)`", site_text(), re.M))
    documented |= set(re.findall(r"^pact (\w+)", site_text(), re.M))
    unknown = {v for v in documented if f"pact {v}" not in helped}
    assert not unknown, f"the site documents verbs the binary does not have: {sorted(unknown)}"


def test_the_check_output_the_site_shows_is_the_output_check_gives() -> None:
    binary = REPO / "target/debug/pact"
    if not binary.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(binary), "check", str(REPO / "examples/refund-desk")],
        capture_output=True, text=True, cwd=REPO,
    ).stdout
    settings = re.search(r"\((\d+) settings\)", out)
    assert settings, f"could not read a settings count from: {out!r}"
    quoted = {int(n) for n in re.findall(r"\((\d+) settings\)", site_text())}
    assert int(settings.group(1)) in quoted, (
        f"the site shows {sorted(quoted)} settings and `pact check` reports "
        f"{settings.group(1)}"
    )


# ───────────────────────────────────────────────── what the site says about Eve


def test_the_eve_measurements_match_the_source_on_disk() -> None:
    """The comparison page's numbers come from a tree that is present. If the
    corpus is gone the claims become unfalsifiable, which is worse than absent."""
    eve = REPO / "research/repos/frameworks/vercel-eve/packages/eve/src"
    if not eve.exists():
        pytest.skip("the Eve corpus is not on this machine")
    files = [p for p in eve.rglob("*.ts")
             if "node_modules" not in p.parts and not p.name.endswith(".test.ts")]
    lines = sum(sum(1 for _ in p.open(errors="ignore")) for p in files)
    text = site_text()
    assert f"{lines:,}" in text, f"the site should quote {lines:,} non-test lines"
    assert f"{len(files):,}" in text, f"the site should quote {len(files):,} non-test files"


def test_the_site_does_not_claim_eve_has_something_it_has_none_of() -> None:
    """Four absences the comparison rests on. If any became non-zero the page
    would be wrong and nobody would notice."""
    eve = REPO / "research/repos/frameworks/vercel-eve/packages/eve/src"
    if not eve.exists():
        pytest.skip("the Eve corpus is not on this machine")
    for term in ("a2a", "agent-card", "acp"):
        hits = [
            p for p in eve.rglob("*.ts")
            if "node_modules" not in p.parts
            and not p.name.endswith(".test.ts")
            and term in p.read_text(errors="ignore").lower()
        ]
        assert not hits, f"the site says Eve has 0 files matching `{term}` and it has {len(hits)}"


# ────────────────────────────────────────────────────────── honesty about gaps


def test_the_gaps_page_names_the_things_that_are_actually_unbuilt() -> None:
    """A site whose gaps page goes stale is worse than one with no gaps page,
    because it converts an honest omission into a false assurance."""
    gaps = (SITE / "status/gaps.md").read_text()
    for unbuilt in ("bundle.from:", "human trial"):
        assert unbuilt in gaps, f"`{unbuilt}` is unbuilt and the gaps page must say so"


def test_bundle_from_is_still_unresolved_so_the_gaps_page_is_still_right() -> None:
    """The check that flips when the gap closes. When `from:` starts resolving,
    this fails and whoever closed it is told to update the page."""
    src = (REPO / "crates/pact-loader/src/bundles.rs").read_text()
    assert "Nothing mounted yet" in src or "nothing mounted" in src.lower(), (
        "bundles.rs no longer says it skips an unmounted bundle — if `from:` now "
        "resolves, remove that blocker from status/gaps.md and the roadmap"
    )


# ────────────────────────── the README and the FRD, which the above did not cover
#
# Every false claim this repo has shipped lived in one of these two files, and
# the check above reads neither. Three were found by an audit rather than by a
# test: the README claimed SLOs stop a run (they report), showed output no
# shipped command produces, and quoted a requirement count the FRD had already
# corrected. A documentation check that covers only the pages nobody was wrong
# about is not a check.

README = REPO / "README.md"
FRD = REPO / "docs/30-FRD.md"


def test_the_readme_does_not_claim_a_construct_the_code_deleted() -> None:
    """`SloBreach` was a mid-run exception that nothing ever built. It was
    deleted, `slo.py` records why, and the README went on describing it.

    Named constructs are checked rather than prose because a name is
    falsifiable: if it is not in `src/`, no document may say the system has it.
    """
    src = "\n".join(
        p.read_text() for p in (REPO / "adapters/python/src").rglob("*.py")
    )
    for gone in ("SloBreach", "Budget("):
        if gone in src:
            continue
        assert gone not in README.read_text(), (
            f"README names `{gone}`, which does not exist in the adapter source. "
            f"Either the construct came back or the paragraph outlived it — the "
            f"second is what happened last time."
        )


def test_the_readme_does_not_promise_slo_enforcement_slo_py_denies() -> None:
    """The specific claim, held against the module's own first sentence."""
    slo = (REPO / "adapters/python/src/pact_adapters/slo.py").read_text()
    reports_only = "does not stop a run" in slo
    readme = README.read_text()
    if reports_only:
        assert "SLOs are enforced during the run" not in readme, (
            "slo.py says it reports and does not stop a run; the README says the "
            "opposite. One of them is wrong and it is not the code."
        )


def test_the_requirement_count_is_the_one_the_frd_computes() -> None:
    """The README quoted 107 for several rounds after the FRD recomputed 120 —
    and the FRD's own note says the README repeated the stale number twice."""
    total = re.search(r"\|\s*\*\*Total\*\*\s*\|\s*\*\*(\d+)\*\*", FRD.read_text())
    assert total, "the FRD should carry a computed total row"
    quoted = {int(n) for n in re.findall(r"(\d+) functional requirements", README.read_text())}
    assert quoted == {int(total.group(1))}, (
        f"README says {sorted(quoted)} functional requirements; the FRD computes "
        f"{total.group(1)} from its own rows"
    )


def test_output_the_readme_shows_is_attributed_to_something_that_can_produce_it() -> None:
    """A transcript in a README reads as "run this and see". The portability
    report comes from `resolve()`, which has no shipped caller — so the block is
    only honest while the text beside it says where it came from."""
    readme = README.read_text()
    if "PORTABILITY: PASS" not in readme:
        return
    src = (REPO / "adapters/python/src/pact_adapters/scoring.py").read_text()
    shipped = "from .resolve import" in src and "resolve(" in src.split("from .resolve import")[1]
    if not shipped:
        assert "no shipped command" in readme or "test suite" in readme, (
            "the README shows a PORTABILITY report and no shipped command produces "
            "one — say so beside the block, or wire `resolve()` and delete this"
        )


# ─────────────────────────── the worked example, counted rather than remembered


def _example_files() -> list[Path]:
    """Every authored file in the worked example.

    `.pact/` is excluded because it is DERIVED (D2) — a workspace that has been
    run has one, and D2 says deleting it must be harmless, so it is not part of
    what the author wrote.
    """
    root = REPO / "examples" / "refund-desk"
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and ".pact" not in p.relative_to(root).parts
    )


def test_the_file_count_the_site_states_is_the_number_of_files() -> None:
    """Two pages gave two different answers — `index.md` said 44 and
    `concepts/what.md` said 43 — and neither was checked against the tree. 43 was
    right, so the front page was wrong about the size of the one example it
    shows."""
    counted = len(_example_files())
    for page in ("site-docs/index.md", "site-docs/concepts/what.md"):
        text = (REPO / page).read_text()
        assert f"{counted} files" in text or f"{counted} authored files" in text, (
            f"{page} does not state the real file count ({counted}) for "
            f"examples/refund-desk"
        )


def test_no_page_claims_the_example_contains_no_code_while_it_does() -> None:
    """`README.md`, `site-docs/index.md` and `site-docs/concepts/what.md` all said
    the worked example had *"no code in it at all"*.

    It has six lines of Python — `skills/refund-policy/scripts/check_window.py` —
    and the example's OWN `README.md` documents it twice. The claim the thesis
    actually supports is narrower and still strong: nothing about authoring the
    agent requires code. Saying the stronger thing made the front page false
    about its own example, which is the cheapest possible way to lose a reader.
    """
    code = [p for p in _example_files() if p.suffix in {".py", ".js", ".ts", ".sh", ".rb"}]
    assert code, (
        "this test assumes the example ships exactly one payload script; if that "
        "is no longer true, the sentences it guards need rewriting, not this "
        "assertion relaxing"
    )
    for page in ("README.md", "site-docs/index.md", "site-docs/concepts/what.md"):
        text = (REPO / page).read_text()
        for false_claim in (
            "no code in it at all",
            "no code anywhere in it",
            "zero code",
        ):
            assert false_claim not in text, (
                f"{page} claims {false_claim!r}, but the example contains "
                f"{', '.join(str(p.relative_to(REPO)) for p in code)}"
            )


# ───────── the numbers the status pages state, against the tree


def test_the_agent_count_the_site_states_is_the_number_of_agents() -> None:
    """`verified.md` said *"One folder"* long after the golden set became 28
    agents across 9 workspaces.

    That direction of staleness is the quieter one — a page understating what
    works costs nobody anything immediately, and is exactly as untrue as a page
    overstating it. Both are a document nothing compares to the tree.
    """
    pact = REPO / "target" / "debug" / "pact"
    if not pact.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    roots = sorted(p.parent for p in (REPO / "examples").rglob("workspace.yaml"))
    agents = 0
    for root in roots:
        out = subprocess.run(
            [str(pact), "show", str(root)], capture_output=True, text=True, check=True
        )
        agents += len(json.loads(out.stdout).get("agents", {}))

    said = (REPO / "site-docs" / "status" / "verified.md").read_text()
    assert f"**{agents} agents across {len(roots)} workspaces**" in said, (
        f"the tree has {agents} agents in {len(roots)} workspaces and "
        f"verified.md does not say so"
    )


def test_the_orchestration_patterns_the_roadmap_names_are_the_ones_that_ship() -> None:
    """The roadmap said PACT *"does not have debate, blackboard, market,
    voting"*. Debate and voting shipped; blackboard and market are refused with
    reasons. A roadmap describing a system two changes ago is a roadmap nobody
    can plan against."""
    on_disk = sorted(
        p.name for p in (REPO / "examples" / "patterns").iterdir() if p.is_dir()
    )
    said = (REPO / "site-docs" / "status" / "roadmap.md").read_text()
    for shape in on_disk:
        assert shape in said, (
            f"`examples/patterns/{shape}/` ships and the roadmap does not "
            f"mention it"
        )
    # And the three that are refused must still be named as refused, or a reader
    # cannot tell "not yet" from "not ever".
    for refused in ("blackboard", "market"):
        assert refused in said, f"{refused} is refused and the roadmap is silent"
    assert "refused rather than pending" in said
