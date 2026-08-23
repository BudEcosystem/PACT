"""A set of documents the second port never opened is named, in its own words.

`knowledge:` declares documents an agent looks things up in, and PACT retrieves
nothing itself. So a run that consulted nothing is the ORDINARY state — and it
must not be the SILENT one, because the agent then answers from what the model
already knew and nobody is told the corpus was never opened.

The reference port says so on `RunResult.unretrieved`, the fifth honesty
channel. The second port had four channels' worth of that machinery and no fifth:
`must-cite: yes` was honoured (the turn is refused before a model call, in the
same words, which is why `knowledge:` is in §7.28's list A), and a corpus WITHOUT
`must-cite` ran, answered, and reported nothing at all. Measured on the shipped
tree `examples/answers-from-documents` with `must-cite` set to `no`:

```text
PYTHON halted: final | output: 25 days.
PYTHON unretrieved: [
  "'staff-handbook' is a set of documents and nothing in this run looked
   anything up in it, so the answer comes from what the model already knew.
   fix: run this where a retrieval runtime serves
   `knowledge/staff-handbook/documents/`, or take `staff-handbook` off this
   agent's `uses:` line."
]
NODE halted: final | output: 25 days.
NODE unenforced: []
NODE keys: ['halted', 'lattice', 'offered', 'output', 'phases', 'stoppedBy',
            'told', 'trace', 'unenforced', 'unmetered', 'waitingWords']
NODE unretrieved: <<NO SUCH FIELD>>
```

Both ports answered "25 days." out of the model's own memory. One of them said
so. That is a fifth honesty channel existing in one port only, on the port whose
entire justification is that it says what it is smaller by (T7).

WHICH CHANNEL, and why it is not `unenforced`. The second port already has a
list for *"this line is read correctly and this runtime does not do it"*, and
this does not go on it, for the reason `unretrieved` is not `unenforced` in the
reference port: **a rule that could not be evaluated sends the reader to the
rule; a corpus that was never read sends them to whoever runs the thing.** The
author's document is not wrong — nothing in it needs editing — and every
sentence on `unenforced` invites an edit (`fix: write answers-with-mode:
prompted`, *"the model is asked to behave however its own default says"*). Filing
this there would route the ticket to the author when the only person who can act
is whoever chose the runtime. And the two ports would then put ONE fact in TWO
different channels for the same document, which is the divergence the
conformance driver exists to catch.

Mutation: delete the `neverLookedIn(spec)` call that fills `unretrieved` in
`adapters/typescript/src/harness.ts` (`const unretrieved = neverLookedIn(spec);`
→ `const unretrieved: string[] = [];`). Without it, the four other channels stay
green, `test_the_subset_the_second_port_runs.py` stays green, the byte-identical
trace comparison in `test_the_golden_set_runs_everywhere.py` stays green — both
ports still answer "25 days." — and only this file goes red.

Mutation, the second: restore `f"{corpus.name!r} is a set of documents…"` in
`adapters/python/src/pact_adapters/harness.py` in place of the typed quotes.
Without it, `staff-handbook` still agrees across the two ports and the whole
rest of the suite stays green — `repr` and typed single quotes coincide on
every name in the shipped trees — and only the `bob's-handbook` and
`the boss's handbook` cases of the two parametrised tests below go red, which
is the point of running the same claim over more than one name.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.ports import tool_payload  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "answers-from-documents"
SHIPPED = "staff-handbook"
TS_DIR = REPO / "adapters" / "typescript"
PACT = REPO / "target" / "debug" / "pact"

ASKED = "how much leave?"
ANSWER = "25 days."

#: Names a corpus folder is allowed to have, and which a person plausibly types.
#: `staff-handbook` is the shipped one. The other two are here because a name is
#: not a slug: the checker accepts an apostrophe and a space, `pact check` on a
#: tree carrying either says *"loaded cleanly"*, and a sentence built with
#: Python's `!r` then spells the first one with DOUBLE quotes while the second
#: port spells it with single ones. A test that only ever sees `staff-handbook`
#: cannot tell *"the two ports agree"* from *"the two ports agree on this one
#: string"*, because that is the one name where `repr` and typed quotes coincide.
NAMES = [SHIPPED, "bob's-handbook", "the boss's handbook"]


def tree_named(root: Path, corpus: str) -> Path:
    """The shipped tree on disk with the corpus renamed, checked before it is used.

    Built as FILES and loaded through the real `pact check` / `pact show` rather
    than by editing the JSON, because the claim being tested is about names an
    author can actually get past the checker. A name this refuses is a name
    neither port will ever see, and the parametrised case would be theatre.
    """
    if not PACT.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    tree = root / "tree"
    shutil.copytree(EXAMPLE, tree, ignore=shutil.ignore_patterns(".pact"))
    if corpus != SHIPPED:
        old = tree / "knowledge" / SHIPPED
        old.rename(old.parent / corpus)
        new = tree / "knowledge" / corpus
        (new / f"{SHIPPED}.yaml").rename(new / f"{corpus}.yaml")
        agent = tree / "agents" / "helpdesk" / "agent.yaml"
        agent.write_text(agent.read_text().replace(SHIPPED, corpus))
    ok = subprocess.run([str(PACT), "check", str(tree)], capture_output=True, text=True)
    assert ok.returncode == 0, (
        f"the checker refused a corpus named {corpus!r}, so no run ever sees it — "
        f"drop the name from NAMES rather than asserting about it:\n{ok.stdout}{ok.stderr}"
    )
    return tree


def document(must_cite: str | None, tree: Path | None = None, corpus: str = SHIPPED) -> dict:
    """The tree, as the loader hands it to an adapter.

    `must_cite=None` leaves the example exactly as it ships (`must-cite: yes`);
    a string overwrites the line, which is how the ordinary corpus — declared,
    never read, and not required to be cited — is reached without a second
    example tree.
    """
    if not PACT.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT), "show", str(tree or EXAMPLE)], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    doc = json.loads(out.stdout)
    if must_cite is not None:
        doc["knowledge"][corpus]["must-cite"] = must_cite
    return doc


def here(spec: AgentSpec):
    return asyncio.run(
        run(spec, ReferenceTransport(Script([Turn(ANSWER, ())])), ASKED, {})
    )


def there(spec: AgentSpec) -> dict:
    """The same agent through the second port, over the same script.

    The payload carries what `test_the_golden_set_runs_everywhere.py` carries,
    because a field the payload never sends is a field the second port cannot
    honour — and the divergence then looks like a bug in the port rather than a
    hole in the driver.
    """
    payload = json.dumps({
        "name": spec.name,
        "instructions": spec.instructions,
        "tools": [tool_payload(t) for t in spec.tools],
        "maxSteps": spec.max_steps,
        "knowledge": [
            {
                "name": k.name, "description": k.description,
                "must-cite": k.must_cite, "passages-at-most": k.passages_at_most,
                "looked-up-by": k.looked_up_by, "split-by": k.split_by,
            }
            for k in spec.knowledge
        ],
    })
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         payload, json.dumps({"turns": [{"text": ANSWER}]}), ASKED, "{}"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    return json.loads(out.stdout)


def first_sentence(line: str) -> str:
    """Everything up to the remedy — the FACT, which both ports must state alike."""
    return line.split(" fix:")[0]


# ------------------------------------------------------- the corpus nobody read


def test_the_second_port_names_the_set_of_documents_it_never_looked_in() -> None:
    """The whole defect, on the shipped tree with the citation rule relaxed.

    A corpus with no `must-cite:` is the ordinary enterprise shape — look it up
    if you can, answer anyway if you cannot — and it is exactly the shape whose
    absence is invisible. The turn succeeds, the answer reads perfectly, and the
    documents the author declared were never opened.
    """
    spec = AgentSpec.from_document(document("no"), "helpdesk")
    out = there(spec)

    assert out["halted"] == "final", out
    assert out["output"] == ANSWER, out
    assert "unretrieved" in out, (
        "the second port answered out of the model's own memory and reported no "
        "such thing: a set of documents this run never consulted is the ordinary "
        "state and must never be the silent one.\n"
        f"  what it did report: {sorted(out)}\n"
        "  fix: fill `RunResult.unretrieved` in adapters/typescript/src/harness.ts "
        "with one sentence per declared `knowledge:` entry, and project it from "
        "`run-trace.ts` — the reference port has carried it since A7."
    )
    said = out["unretrieved"]
    assert said, f"a corpus nothing looked in must never be silent: {out}"
    assert "staff-handbook" in said[0], said
    assert "fix:" in said[0], f"and it has to say what to do about it: {said[0]}"


@pytest.mark.parametrize("corpus", NAMES)
def test_the_two_ports_state_the_same_absence_in_the_same_words(
    corpus: str, tmp_path: Path
) -> None:
    """One fact, one sentence, whichever runtime the folder was run on.

    The remedies differ and are allowed to: the reference port takes a
    `retrieved_by` from a host that retrieves, and nothing handed to this one
    ever will, so its `fix:` sends the reader somewhere else. What may not
    differ is the sentence BEFORE it — two ports describing the same absence in
    two ways is the specification ambiguity this suite exists to find.

    Run over three names, and not over the shipped one alone, because the first
    version of this test could not tell agreement from coincidence. `harness.py`
    built the sentence with `{corpus.name!r}`, which quotes `staff-handbook` with
    single quotes and `bob's-handbook` with double ones, while the second port
    types the quotes; the checker loads both names, so an author with an
    apostrophe in a folder name got two ports describing one absence two ways and
    nothing was red. Measured before the fix, on a copy of the shipped tree:

    ```text
    PY  : "bob's-handbook" is a set of documents and nothing in this run …
    NODE: 'bob's-handbook' is a set of documents and nothing in this run …
    PREFIX EQUAL: False
    ```

    The `must-cite` refusal path already agreed on that same name — `_and_list`
    types its quotes — so the odd one out was this sentence, in the port the
    other one is held against.
    """
    tree = tree_named(tmp_path, corpus)
    spec = AgentSpec.from_document(document("no", tree, corpus), "helpdesk")
    mine = list(here(spec).unretrieved)
    node = there(spec)["unretrieved"]

    assert len(node) == len(mine) == 1, (mine, node)
    assert first_sentence(node[0]) == first_sentence(mine[0]), (
        f"the two ports describe one absence differently, for a corpus named {corpus!r}:\n"
        f"  python: {mine[0]}\n"
        f"  node:   {node[0]}\n"
        "  fix: the fact is the same on both runtimes — make the sentence before "
        "`fix:` the same too, and let only the remedy differ. Quote the name by "
        "typing the quotes, on both sides: a name is not a slug, and a formatter "
        "that picks the quote character off the name spells one absence two ways."
    )
    assert "fix:" in node[0] and "fix:" in mine[0], (mine, node)
    assert f"'{corpus}'" in mine[0], (
        f"the reference port did not quote {corpus!r} the way every other sentence "
        f"about a corpus quotes it — `_and_list`, `neverLookedIn` and the CLI all "
        f"type single quotes:\n  {mine[0]}"
    )


@pytest.mark.parametrize("corpus", NAMES)
def test_a_refusal_and_a_report_name_the_same_corpus_the_same_way(
    corpus: str, tmp_path: Path
) -> None:
    """One name, one spelling, in both sentences a person can be shown.

    The `must-cite` refusal (*"I could not read '…'"*) and the `unretrieved`
    report are the two places a corpus name reaches a reader, and for a round
    `harness.py` spelt them differently in the same file for the same corpus —
    `_and_list` types its quotes, the report used `!r`. A reader who sees
    `"bob's-handbook"` in one line and `'bob's-handbook'` in the next has been
    given a reason to wonder whether they are the same thing.
    """
    tree = tree_named(tmp_path, corpus)
    refused = here(AgentSpec.from_document(document(None, tree, corpus), "helpdesk"))
    reported = here(AgentSpec.from_document(document("no", tree, corpus), "helpdesk"))

    assert refused.halted == "no-sources", refused.halted
    quoted = f"'{corpus}'"
    assert quoted in refused.output, (
        f"the refusal did not name the corpus as {quoted}:\n  {refused.output}"
    )
    assert quoted in reported.unretrieved[0], (
        "one file spells one corpus name two ways:\n"
        f"  refusal: {refused.output}\n"
        f"  report:  {reported.unretrieved[0]}\n"
        "  fix: type the quotes in both — `!r` picks its quote character off the "
        "name, so a name with an apostrophe in it comes out spelt differently."
    )


def test_the_absence_is_not_also_filed_as_a_rule_this_port_does_not_apply() -> None:
    """The channel separation, asserted rather than assumed.

    `unenforced` sends the reader to the author's line; this sends them to
    whoever runs the thing. Reporting the corpus on both would tell an author to
    edit a document that is not wrong, and would put one fact in two channels on
    one of the two ports.
    """
    spec = AgentSpec.from_document(document("no"), "helpdesk")
    out = there(spec)
    stray = [line for line in out["unenforced"] if "staff-handbook" in line]
    assert not stray, (
        "the corpus is reported on `unenforced` as well:\n  " + "\n  ".join(stray)
        + "\n  fix: `unretrieved` is the channel for a corpus nobody read — a "
        "reader of `unenforced` edits their own document, and there is nothing "
        "in it to edit."
    )
    assert list(here(spec).unenforced) == [], here(spec).unenforced


def test_a_refused_turn_still_says_which_documents_were_never_opened() -> None:
    """The example exactly as it ships: `must-cite: yes`, and nothing retrieved.

    The turn is refused before a model call — both ports already agree on that,
    which is why `knowledge:` is in §7.28's list A. What the refusal must not
    lose is WHY: a run that stops with "I have nothing to answer from" and an
    empty `unretrieved` has named the outcome and not the cause, and the reader
    is left to guess which of the declared sets was the missing one.
    """
    spec = AgentSpec.from_document(document(None), "helpdesk")
    out = there(spec)
    mine = here(spec)

    assert out["halted"] == mine.halted == "no-sources", (out["halted"], mine.halted)
    assert out["output"] == mine.output, (out["output"], mine.output)
    assert out["unretrieved"], (
        "the run refused for want of sources and did not say which set it could "
        "not read.\n"
        f"  it said: {out['output']}\n"
        "  fix: fill `unretrieved` before the `must-cite` refusal returns, as "
        "`harness.py` does — the refusal is the outcome, the channel is the cause."
    )
    assert first_sentence(out["unretrieved"][0]) == first_sentence(mine.unretrieved[0])


def test_an_agent_that_declares_no_documents_is_told_nothing() -> None:
    """A report that fires on every run stops being read.

    The channel has to be a channel and not a banner: an agent with no
    `knowledge:` at all comes back with it empty, which is what makes the
    sentence above mean something when it appears.
    """
    quiet = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         json.dumps({
             "name": "Refund Desk", "instructions": "Decide.", "tools": [],
             "maxSteps": 2,
         }),
         json.dumps({"turns": [{"text": ANSWER}]}), ASKED, "{}"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if quiet.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {quiet.stderr[-300:]}")
    out = json.loads(quiet.stdout)
    assert out["unretrieved"] == [], (
        f"an agent that declares no documents was told about some anyway: {out}"
    )
