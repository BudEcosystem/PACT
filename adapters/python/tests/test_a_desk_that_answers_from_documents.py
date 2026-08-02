"""`knowledge:` — the commonest enterprise shape, which could not be written (A7).

An agent that answers out of a set of documents and says which one it used. Until
this kind existed there was no line for it: `uses:` named tools and skills, and a
corpus is neither. A skill is read end to end; this is looked things up in.

PACT does not retrieve, embed, index or chunk. A runtime that does all four
already exists — this declares what that runtime needs to know and governs the
part a reviewer has to be able to read, which is the §4 declared-and-delegated
pattern `port.through:` and the durable store already use.

Every other §4 row pairs the declaration with a channel. This one pairs it with
`unretrieved`, a FIFTH honesty channel, and with the one thing that is not a
report: `must-cite: yes` on a set the run could not consult FAILS THE TURN.
Answering anyway gives an answer from what the model already knew, citing a
document it never opened — the worst outcome available and the one that looks
most like success.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "answers-from-documents"
PACT = REPO / "target" / "debug" / "pact"


def document() -> dict:
    out = subprocess.run([str(PACT), "show", str(EXAMPLE)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def spec() -> AgentSpec:
    return AgentSpec.from_document(document(), "helpdesk")


def answering(**kw):
    return asyncio.run(
        run(spec(), ReferenceTransport(Script([Turn("25 days.", ())])), "how much leave?", {}, **kw)
    )


def test_the_worked_rag_example_loads_cleanly() -> None:
    out = subprocess.run(
        [str(PACT), "check", str(EXAMPLE), "--deny-warnings"], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_documents_reach_the_spec_as_files_and_not_as_settings() -> None:
    """Kept as FILES so a table stays a table — and so the loader digests them,
    which is what makes "these are the documents" checkable rather than
    asserted. It is also why `documents:` is a folder and not a glob: there is
    no path type in this language, and a glob's file order is load-bearing for a
    digest the loader promises is reproducible on any machine."""
    s = spec()
    assert len(s.knowledge) == 1
    corpus = s.knowledge[0]
    assert corpus.name == "staff-handbook"
    assert set(corpus.documents) == {"leave.md", "expenses.md"}


def test_what_governs_the_lookup_reaches_the_spec() -> None:
    corpus = spec().knowledge[0]
    assert corpus.must_cite is True
    assert corpus.passages_at_most == 3
    assert corpus.looked_up_by == "words"


def test_a_set_the_run_could_not_consult_is_reported_and_never_silent() -> None:
    """The fifth channel. A fifth rather than a fifth use of `unenforced`, for
    the reason `never_reached` is not `unmetered`: "the rule could not be
    evaluated" sends the author to the rule, "the corpus was never read" sends
    them to whoever runs the thing."""
    doc = document()
    doc["knowledge"]["staff-handbook"]["must-cite"] = "no"
    r = asyncio.run(
        run(
            AgentSpec.from_document(doc, "helpdesk"),
            ReferenceTransport(Script([Turn("25 days.", ())])),
            "how much leave?",
            {},
        )
    )
    assert r.unretrieved, "a corpus nothing looked in must never be silent"
    assert "staff-handbook" in r.unretrieved[0]
    assert "fix:" in r.unretrieved[0], "and it has to say what to do"


def test_must_cite_on_a_corpus_nothing_read_fails_the_turn() -> None:
    r = answering()
    assert r.halted == "no-sources", r.halted
    assert "staff-handbook" in r.output
    assert "nothing to answer from" in r.output


def test_nothing_is_paid_for_before_the_sources_are_known_to_be_missing() -> None:
    """Decided before a single model call. Paying for an answer that cannot be
    given is the other thing that would look like working."""
    r = answering()
    assert r.steps == [], r.steps


def test_with_a_runtime_that_did_retrieve_the_turn_goes_through() -> None:
    r = answering(retrieved_by={"staff-handbook": ["Everyone gets 25 days of annual leave."]})
    assert r.halted == "final", r.halted
    assert r.output == "25 days."
    assert r.unretrieved == ()


def test_looking_up_by_meaning_needs_an_embedder_to_be_allowed_out() -> None:
    """`meaning` needs a model to work out what a question is about, and that
    model is outside this box. `embedder` was the one `allow-egress:` role with
    no producer anywhere in the tree; this is its first."""
    import shutil
    import tempfile

    dst = Path(tempfile.mkdtemp()) / "meaning"
    shutil.copytree(EXAMPLE, dst)
    p = dst / "knowledge/staff-handbook/staff-handbook.yaml"
    p.write_text(p.read_text().replace("looked-up-by: words", "looked-up-by: meaning"))
    out = subprocess.run([str(PACT), "check", str(dst)], capture_output=True, text=True)
    said = out.stdout + out.stderr
    assert out.returncode != 0, said
    assert "loader/reaches-outside-the-box" in said, said
    assert "embedder" in said, "the fix names the role to add"
    assert "looked-up-by: words" in said, "and the alternative that needs nothing outside"
    shutil.rmtree(dst.parent)


def test_a_set_of_documents_with_no_documents_is_refused() -> None:
    import shutil
    import tempfile

    dst = Path(tempfile.mkdtemp()) / "empty"
    shutil.copytree(EXAMPLE, dst)
    shutil.rmtree(dst / "knowledge/staff-handbook/documents")
    out = subprocess.run([str(PACT), "check", str(dst)], capture_output=True, text=True)
    said = out.stdout + out.stderr
    assert "loader/knowledge-with-no-documents" in said, said
    assert "answer from what the model already knew" in said
    shutil.rmtree(dst.parent)


def test_a_typo_in_uses_teaches_the_construct_to_somebody_who_never_heard_of_it() -> None:
    """The strongest thing the design claimed, and it costs no Rust: the existing
    name-resolution diagnostic starts naming `knowledge:` and offering the file
    to write."""
    import shutil
    import tempfile

    dst = Path(tempfile.mkdtemp()) / "typo"
    shutil.copytree(EXAMPLE, dst)
    p = dst / "agents/helpdesk/agent.yaml"
    p.write_text(p.read_text().replace("staff-handbook", "staff-handbok"))
    out = subprocess.run([str(PACT), "check", str(dst)], capture_output=True, text=True)
    said = out.stdout + out.stderr
    assert "`knowledge:`" in said, said
    assert "knowledge/staff-handbok" in said, "and the file to write"
    # And the sentence is grammatical: `or_list`, not `.join(" or ")`.
    assert "`tools:`, `skills:` or `knowledge:`" in said, said
    shutil.rmtree(dst.parent)


def test_a_stage_can_narrow_to_a_set_of_documents() -> None:
    """An agent that may use a corpus and a loop that cannot narrow to one is an
    asymmetry, and the schema has a test for exactly that shape."""
    schema = yaml.safe_load((REPO / "spec/schema.yaml").read_text())["groups"]
    assert "knowledge" in schema["stage"]["fields"]["may-use"]["names"]
    assert "knowledge" in schema["agent"]["fields"]["uses"]["names"]
    assert "knowledge" in schema["variant"]["fields"]["may-use"]["names"]
