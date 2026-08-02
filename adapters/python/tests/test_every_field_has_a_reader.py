"""Every field the schema accepts is read by something, or is declared delegated.

Four mechanisms have shipped built, tested and unreachable — interceptors (a
chain built empty), context-policy (resolved, never consulted), the model pin
(parsed, never used) and the team budget (a parameter no caller supplied). Each
was found one at a time, after the fact, by an adversarial pass. A fifth,
`survives-shortening:`, was found by the audit this test comes from.

The pattern is always the same and it always passes review: the mechanism is
correct, its tests construct its object directly, and nothing on the authored
path ever builds one. A test that constructs the object proves the object works
and says nothing about whether the author's line reaches it.

This is the instrument instead of the vigilance. A field an author can write and
no runtime reads is either a defect or a delegation, and delegation has to be
said out loud.
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "adapters/python/src/pact_adapters"
TS = REPO / "adapters/typescript/src"
CRATES = REPO / "crates"

SCHEMA = yaml.safe_load((REPO / "spec/schema.yaml").read_text())["groups"]


def _shipping_files() -> list[Path]:
    """Everything that could legitimately read an authored field.

    A file under a `tests/` directory is excluded, not only one whose *name*
    contains "test". The old rule kept 56 of 139 files — a fixture that writes a
    field is not a runtime that reads it, and counting fixtures is how a dead
    field looks alive.
    """
    out = []
    for root, glob in ((SRC, "*.py"), (TS, "*.ts"), (CRATES, "*.rs")):
        for p in root.rglob(glob):
            if "test" in p.name or ".venv" in p.parts or "tests" in p.parts:
                continue
            out.append(p)
    return out


def _identifiers_only(text: str, suffix: str) -> str:
    """The same file with every comment and every string literal removed.

    This is the half of the corpus where an identifier means an identifier. It
    exists because English is not evidence: `callable.rs` contains the sentence
    "so the first thing this agent tries to do fails before a word is written",
    and that sentence alone was enough to report the field `tries:` as read.
    """
    if suffix == ".py":
        text = re.sub(r"#.*", "", text)
        text = re.sub(r'"""(?:.|\n)*?"""', '""', text)
        text = re.sub(r"'''(?:.|\n)*?'''", "''", text)
        text = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', text)
        text = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", text)
        return text
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*(?:.|\n)*?\*/", "", text)
    if suffix == ".rs":
        text = re.sub(r'r#"(?:.|\n)*?"#', '""', text)
        # Rust string literals span lines, and the two names this rule was
        # written for were both matched in the TAIL of a multi-line one.
        return re.sub(r'"(?:[^"\\]|\\(?:.|\n))*"', '""', text)
    text = re.sub(r"`(?:[^`\\]|\\(?:.|\n))*`", "``", text)
    text = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', text)
    return re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", text)


def sources() -> str:
    """Every shipping file, whole. Where a key lookup lives."""
    return "\n".join(p.read_text(errors="ignore") for p in _shipping_files())


def identifiers() -> str:
    """Every shipping file with prose removed. Where an identifier lives."""
    return "\n".join(
        _identifiers_only(p.read_text(errors="ignore"), p.suffix)
        for p in _shipping_files()
    )


#: Fields no runtime reads, on purpose, each with the reason.
#:
#: This list is the point of the test. Adding to it is cheap and must therefore
#: be deliberate: a line here is a claim that the field is somebody else's job,
#: and it is reviewable precisely because it is written down rather than being
#: the silent default.
DELEGATED: dict[str, str] = {
    # Read by the loader and the CLI in Rust, never by a Python runtime.
    "workspace.workspace-id": "identity, used by the host's registry",
    "workspace.owner": "governance metadata for a reviewer, not the run",
    # `workspace.profile` was here, delegated on the grounds that it "selects
    # defaults at check time". Nothing in the CLI reads it — `grep -rn profile
    # crates/` returns nothing. It is a KNOWN_GAP, not a delegation, and this
    # entry is the exact failure this file exists to prevent, one level up: a
    # claim that somebody else does it, believed because it was written down.
    # Documentation-shaped: they exist to be read by a person.
    "agent.description": "read by a person and by `pact card`",
    "tool.description": "shown to the model through the tool definition",
    "action.description": "shown to the model",
    "skill.description": "shown to the model",
    "skill.costs-about": "an estimate for a reviewer deciding whether to load it",
    # Named in `docs/50-NOT-COPIED.md` §4 — PACT declares, the host executes.
    "port.who-can-reach-it": "§4 row: 'Seven ways of verifying a caller' — the host does the checking",
    "port.same-conversation-when": "§4 ports row: what makes two messages one conversation is the connector's",
    "state.never-from": "§4 row: the store refuses a write from a source this names",
    "state.shaped-like": "§4 row: the store holds the shape; PACT records what it must be",
    "state.starts-as": "§4 row: the store supplies the first value",
    # Catalogue provenance: it exists so a person can audit where a figure came
    # from. Nothing at run time should behave differently because of it.
    "provenance.recorded-by": "who wrote the figure down, for a reviewer",
    "provenance.contamination": "a caveat on a benchmark figure, for a reviewer",
    # ---- Surfaced when this file stopped counting its own prose as a reader. ----
    #
    # None of the six below is new: each has been unread for as long as it has
    # existed, and each was reported as read because its name occurs in an
    # English sentence somewhere in the tree. They are written down here in the
    # same change that stops the mis-reporting, which is the rule this file
    # states for itself — closing a gap and updating the register are one edit.
    "figure.provenance": (
        "where a catalogue figure came from, for a reviewer. `resolve.py::_window` "
        "refuses a bare integer but reads only `value:` from the block, so the "
        "sub-fields below reach no run"
    ),
    "provenance.as-of": "when the figure was last confirmed, for a reviewer",
    # `port.same-conversation-when` above is delegated on exactly this ground.
    "port.through": (
        "§4 ports row: which connected system carries the traffic is the host's "
        "connector inventory, not something the portable folder can resolve"
    ),
    "resource.auth": (
        "§4 row: a reference to where a credential is kept, which only the "
        "platform that published the reference can resolve. PACT never holds "
        "the credential itself, so there is nothing here for a run to read"
    ),
    # The three `state.*` rows above (`never-from`, `shaped-like`, `starts-as`)
    # are delegated to the store. These two are the same delegation: retention
    # is enforced where the data lives.
    "state.lasts": "§4 row: how long a value survives is the store's to enforce",
    "state.forget-after": (
        "§4 row: the store discards it on this schedule. A retention promise "
        "PACT records and something else keeps"
    ),
}

#: Fields that SHOULD be read and are not. Each is a defect, not a delegation.
#:
#: This list may only shrink. `test_known_gaps_only_shrink` fails when a field
#: here gains a reader, so closing a gap forces the register to be updated in
#: the same change — which is the failure mode `docs/70-PRODUCTION-GAP-REGISTER.md`
#: exists to prevent for itself.
KNOWN_GAPS: dict[str, str] = {
    # EMPTY. The last entry was `workspace.profile`, and it left for a reason
    # worth stating rather than by being fixed: `pact check` now reads it, to
    # warn `loader/profile-selects-nothing` — an author writing
    # `profile: production` is told it changes nothing. By this file's own rule
    # that is a reader, and the rule is right: the field is no longer silent.
    #
    # What remains is NOT "nothing reads it". It is that no profile mechanism
    # exists at all, which is AC-7.2 and lives in the register. A gap that has
    # changed shape belongs where its new shape is described, not here under an
    # old name.
}


def reader_exists(field: str, body: str, code: str | None = None) -> bool:
    """Is this field name read anywhere outside a test?

    Two ways, and each is checked in the half of the corpus where it can mean
    something:

    * **as a key** — the authored spelling in quotes, `"forget-after"`, which is
      how a loader looks a YAML key up. Searched in the WHOLE file, because a
      key lookup is a string literal by nature.
    * **as an identifier** — the snake_case form as a whole word, which is how a
      deserialised struct field is then used. Searched only in the corpus with
      comments and string literals removed.

    The rule this replaces had two more patterns, `` `field` `` and `" field"`,
    and both matched English. Measured against the shipping corpus, they lit
    `tries`, `knowledge`, `documents`, `claim` and `owner` — five names nothing
    reads — from sentences like `callable.rs`'s "the first thing this agent
    tries to do fails". A test that treats its own prose as evidence reports
    every field as read, which is the one answer it must never be able to give.

    **The limit, stated rather than discovered later.** A one-word field whose
    snake form is an ordinary identifier can still be lit by an unrelated use:
    `prompt` is matched by `lambda prompt:` in `optimising.py`. Hyphenated names
    are safe, because no code writes `forget_after` by accident. The residue is
    small and it is the direction that over-reports rather than under-reports.
    """
    if f'"{field}"' in body or f"'{field}'" in body:
        return True
    snake = field.replace("-", "_")
    return re.search(rf"\b{re.escape(snake)}\b", code if code is not None else body) is not None


@lru_cache(maxsize=1)
def corpus() -> tuple[str, str]:
    """Both halves, built once. Eight tests ask for them."""
    return sources(), identifiers()


def fields_of(kind: str) -> list[str]:
    return sorted((SCHEMA.get(kind, {}).get("fields") or {}).keys())


ALL = [(k, f) for k in sorted(SCHEMA) for f in fields_of(k)]


def test_the_schema_has_fields_to_check() -> None:
    assert len(ALL) > 200, f"only {len(ALL)} fields found — the schema did not load"


def test_every_authored_field_is_read_by_something_or_declared_delegated() -> None:
    """The whole test.

    A field an author can write, that nothing reads and nobody declared
    delegated, is a promise the format cannot keep.
    """
    body, code = corpus()
    orphans = [
        f"{kind}.{field}"
        for kind, field in ALL
        if f"{kind}.{field}" not in DELEGATED
        and f"{kind}.{field}" not in KNOWN_GAPS
        and not reader_exists(field, body, code)
    ]
    assert not orphans, (
        f"{len(orphans)} field(s) an author can write are read by no runtime and "
        f"are neither declared delegated nor a known gap:\n  "
        + "\n  ".join(orphans)
        + "\n\nEither wire it, delete it, or add it to DELEGATED with the reason "
        "somebody else does it. A field with no reader is the defect this "
        "project has shipped five times."
    )


@pytest.mark.parametrize("kind", ["agent", "tool", "policy", "interceptor", "state"])
def test_the_kinds_that_carry_behaviour_are_fully_read(kind: str) -> None:
    """The kinds where an unread field is most costly, checked one by one so a
    failure names which kind rather than handing back a list of forty."""
    body, code = corpus()
    orphans = [
        f for f in fields_of(kind)
        if f"{kind}.{f}" not in DELEGATED
        and f"{kind}.{f}" not in KNOWN_GAPS
        and not reader_exists(f, body, code)
    ]
    assert not orphans, f"`{kind}` has unread fields: {orphans}"


def test_delegated_is_not_a_dumping_ground() -> None:
    """Every delegation carries a reason, and the list stays small enough to
    read. A long list of 'somebody else does it' is how the check stops
    meaning anything."""
    assert len(DELEGATED) < 30, (
        f"{len(DELEGATED)} delegations — this list is becoming the exception "
        f"that swallows the rule"
    )
    for field, reason in DELEGATED.items():
        assert len(reason) > 15, f"`{field}` is delegated with no real reason: {reason!r}"
        assert "." in field, f"`{field}` should be spelled `kind.field`"


def test_a_field_named_only_in_a_sentence_the_checker_prints_is_not_a_field_anything_reads() -> None:
    """The instrument's own honesty, checked on a corpus this test controls.

    Every form below names `forget-after` and none of them reads it. Before the
    rule was repaired, the last four all counted, and the whole point of this
    file — that a field with no reader is found rather than assumed — held only
    for names that never appear in an English sentence.

    **The mutation:** put `f" {snake}"` back among the patterns in
    `reader_exists`. The `rust_diagnostic` and `python_docstring` cases go
    green-when-they-should-be-red and this test fails.
    """
    prose = {
        "rust_comment": "// The `forget-after` line is the store's to honour.\n",
        "rust_diagnostic": 'let m = "nothing says when to forget_after this run";\n',
        "python_docstring": '"""Whether a value has a forget_after schedule."""\n',
        "markdown_in_comment": "/// See `forget-after` in docs/50-NOT-COPIED.md\n",
        # The shape that actually caused this. `callable.rs:159` is the TAIL of
        # a Rust string literal opened two lines earlier, and a stripper that
        # stops at a newline leaves the tail behind as if it were code. This is
        # what reported `tries:` and `documents:` as read.
        "rust_multiline_string": (
            'let m = format!(\n'
            '    "{name} names a tool that is not here,\n'
            '     so nothing says when to forget_after this run finishes."\n'
            ');\n'
        ),
    }
    for name, text in prose.items():
        suffix = ".py" if name.startswith("python") else ".rs"
        # Both halves, exactly as `corpus()` supplies them: the prose reaches
        # `body` whole, and only the stripped half reaches `code`. Passing an
        # empty `body` here would make this test unable to fail, which is the
        # first thing the mutation caught.
        assert not reader_exists("forget-after", text, _identifiers_only(text, suffix)), (
            f"`{name}` mentions the field and does not read it, but the rule "
            f"counted it. Prose is not a reader."
        )

    reading = {
        "rust_key_lookup": ('doc.get("forget-after")', ".rs"),
        "python_attribute": ("if spec.forget_after is not None:", ".py"),
        "rust_binding": ("let forget_after = block.remove(&k);", ".rs"),
        "serde_rename": ('#[serde(rename = "forget-after")]', ".rs"),
    }
    for name, (text, suffix) in reading.items():
        assert reader_exists("forget-after", text, _identifiers_only(text, suffix)), (
            f"`{name}` genuinely reads the field and the rule missed it. "
            f"Tightening must not cost a real reader."
        )


def test_a_fixture_that_writes_a_field_is_not_a_runtime_that_reads_it() -> None:
    """`tests/` is excluded from the corpus, and the exclusion is load-bearing.

    The old rule skipped a file only when its *name* contained "test", which
    kept 56 of 139 files — every fixture in `crates/*/tests/`. A workspace
    written to exercise a field is the strongest possible evidence that the
    field is authorable and no evidence at all that anything reads it.
    """
    kept = _shipping_files()
    assert kept, "the corpus is empty — the walk found nothing"
    under_tests = [p for p in kept if "tests" in p.parts]
    assert not under_tests, (
        f"{len(under_tests)} file(s) under a tests/ directory are being counted "
        f"as readers: {[str(p) for p in under_tests[:3]]}"
    )


def test_known_gaps_only_shrink() -> None:
    """A gap that has been closed must be struck off the list in the same change.

    Without this, `KNOWN_GAPS` becomes a place defects go to be forgotten: the
    suite stays green whether or not anybody fixed anything. Here, fixing one
    turns the suite red until the register agrees.
    """
    body, code = corpus()
    fixed = [f for f in KNOWN_GAPS if reader_exists(f.split(".", 1)[1], body, code)]
    assert not fixed, (
        f"these are no longer gaps — something now reads them: {fixed}. "
        f"Remove them from KNOWN_GAPS and from docs/70-PRODUCTION-GAP-REGISTER.md."
    )
