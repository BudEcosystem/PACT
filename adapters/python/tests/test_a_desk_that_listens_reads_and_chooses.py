"""The runtime half of `docs/96-MODALITIES-INTERFACES-TEMPLATES-TURNS.md`.

`pact check` holds the tree; these hold what this package does with it:
Jinja rendered exactly as it was checked, a server's tools recorded by
`pact-sync` with the digest a connection takes, what a run does when the server
changed, and a resolver that never offers an embedder as an agent's model and
ranks by `prefer:`.

The tree is `tests/trees/a-desk-that-listens-reads-and-chooses/`.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters import holes, mcp_bridge, resolve, syncing  # noqa: E402
from pact_adapters.ir import AgentSpec, ResourceSpec  # noqa: E402
from trees import REPO, shown  # noqa: E402

TREE = REPO / "tests/trees/a-desk-that-listens-reads-and-chooses"


# ─────────────────────────────────────────────────────────────── 96 §C: Jinja


def _rust_list(name: str) -> set[str]:
    source = (REPO / "crates/pact-loader/src/jinja.rs").read_text(encoding="utf-8")
    body = source.split(f"pub const {name}: &[&str] = &[", 1)[1].split("];", 1)[0]
    return set(re.findall(r'"([^"]+)"', body))


def test_the_filters_a_template_may_use_are_the_ones_the_checker_allows() -> None:
    assert holes.JINJA_FILTERS == _rust_list("FILTERS")
    assert holes.JINJA_TESTS == _rust_list("TESTS")


def test_the_desks_own_words_are_rendered_from_its_run_inputs() -> None:
    spec = AgentSpec.from_document(shown(TREE), "front-desk", TREE)
    assert spec.template_language == "jinja"
    said = holes.fill(
        spec.instructions,
        run_inputs={"shop-name": "Acme", "tier": "gold", "brand-voice": "warm"},
        remembers={"caller-notes": ["rang about a kettle"]},
        language=spec.template_language,
    )
    assert "You answer the phone for Acme." in said
    assert "offer the free returns label" in said
    assert "Speak as WARM." not in said and "Speak as warm." in said
    assert "- rang about a kettle" in said


def test_a_value_is_quoted_never_rendered_and_a_missing_one_is_refused() -> None:
    said = holes.fill(
        "Hello {{ run_inputs.name }}.",
        run_inputs={"name": "{{ 7*7 }}"},
        language="jinja",
    )
    assert said == "Hello {{ 7*7 }}."
    with pytest.raises(holes.Unfilled):
        holes.fill("Hello {{ run_inputs.name }}.", run_inputs={}, language="jinja")


def test_the_sandbox_reaches_nothing_the_checker_refused() -> None:
    with pytest.raises(Exception):
        holes.fill("{{ ''.__class__ }}", language="jinja")
    with pytest.raises(Exception):
        holes.fill("{{ 'x' | tojson }}", language="jinja")


# ─────────────────────────────────────────────── 96 §E: what the server offers

LISTED = [
    {
        "name": "search_threads",
        "description": "Search the mailbox.",
        "inputSchema": {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "send_email",
        "description": "Send an email.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipient": {"type": "string"},
                "subject": {"type": "string"},
                "html_body": {"type": "string"},
            },
            "required": ["recipient", "subject", "html_body"],
        },
    },
]


def test_the_recorded_digest_is_the_one_a_connection_takes() -> None:
    block = syncing.published_block(LISTED, taken_at=dt.datetime(2026, 10, 27, tzinfo=dt.timezone.utc))
    assert block["digest"] == mcp_bridge.digest_of(LISTED)
    assert block["taken-at"] == "2026-10-27T00:00:00Z"
    assert block["tools"]["send_email"]["takes"]["required"][0] == "recipient"
    # And the fixture was written by this very command, so its pin holds.
    doc = shown(TREE)
    assert doc["resources"]["gmail-server"]["published"]["digest"] == mcp_bridge.digest_of(LISTED)
    pinned = ResourceSpec.from_document(doc, "gmail-server")
    assert pinned.tool_snapshot_digest == block["digest"]
    assert pinned.tool_snapshot_taken_at == "2026-10-27"


def test_a_sync_replaces_only_the_block_it_wrote(tmp_path: Path) -> None:
    root = tmp_path / "w"
    shutil.copytree(TREE, root)
    resource = root / "resources/gmail-server.yaml"
    listed = [dict(LISTED[0]), dict(LISTED[1], description="Send one email.")]
    assert syncing.main(["gmail-server", str(root), "--from-file", str(_json(tmp_path, listed))]) == 0
    text = resource.read_text(encoding="utf-8")
    assert text.count("published:") == 1
    assert "endpoint: host/gmail-mcp" in text and "if-it-changes: use-what-was-reviewed" in text
    assert "Send one email." in text


def _json(tmp_path: Path, listed: list) -> Path:
    import json

    p = tmp_path / "tools.json"
    p.write_text(json.dumps({"tools": listed}), encoding="utf-8")
    return p


def test_a_reworded_tool_does_what_the_resource_says() -> None:
    doc = shown(TREE)
    assert mcp_bridge.when_it_changed(doc, "gmail-server", LISTED).verdict == "same"
    reworded = [dict(LISTED[0], description="Look through the mailbox."), LISTED[1]]
    change = mcp_bridge.when_it_changed(doc, "gmail-server", reworded)
    assert change.verdict == "use-what-was-reviewed" and not change.governing
    assert any("reworded `search_threads`" in w for w in change.why)


def test_a_change_an_approval_rests_on_always_stops() -> None:
    doc = shown(TREE)
    # `send-message` needs a person, and `inspects: [to]` reaches the server as
    # `recipient` through `passes:` — so renaming it is never accepted unasked.
    moved = dict(LISTED[1])
    moved["inputSchema"] = {
        "type": "object",
        "properties": {"to_address": {"type": "string"}, "subject": {"type": "string"}},
    }
    change = mcp_bridge.when_it_changed(doc, "gmail-server", [LISTED[0], moved])
    assert change.governing and change.verdict == "stop"
    doc["resources"]["gmail-server"]["asks-when-it-changes"] = "may-we-carry-on"
    assert mcp_bridge.when_it_changed(doc, "gmail-server", [LISTED[0], moved]).verdict == "ask"


def test_a_new_tool_is_reported_and_never_governs_by_appearing() -> None:
    doc = shown(TREE)
    added = LISTED + [{"name": "delete_everything", "inputSchema": {"type": "object"}}]
    change = mcp_bridge.when_it_changed(doc, "gmail-server", added)
    assert not change.governing
    assert any("delete_everything" in w and "nobody reviewed" in w for w in change.why)


# ─────────────────────────────────────────────── 96 §A2, §B3: the resolver


def test_the_resolver_never_offers_an_embedder_as_an_agents_model() -> None:
    catalogue = resolve.load_catalogue(workspace=TREE)
    rows = {e.name: e for e in catalogue.entries}
    assert rows["nomic-embed-text"].kind == "embedding"
    ok, why = rows["nomic-embed-text"].satisfies({})
    assert not ok and "embedding model" in why
    assert rows["qwen2.5-vl-7b-instruct"].satisfies({"capabilities": ["documents"]})[0]
    assert rows["qwen2.5-vl-7b-instruct"].first_words_ms == pytest.approx(350.0)
    assert rows["qwen2.5-vl-7b-instruct"].scores["MMMU"] == pytest.approx(58.6)


def test_what_the_desk_needs_is_read_off_its_contract_and_its_preference() -> None:
    needs = resolve.needs_of(shown(TREE), "front-desk")
    assert "documents" in needs["capabilities"]
    assert needs["prefer"] == "fastest"


def test_prefer_fastest_ranks_the_soonest_first_words_before_price() -> None:
    quick = resolve.ModelEntry(name="quick", tier="mid", cost=2.0, first_words_ms=200.0)
    cheap = resolve.ModelEntry(name="cheap", tier="mid", cost=0.1, first_words_ms=900.0)
    unmeasured = resolve.ModelEntry(name="unmeasured", tier="mid", cost=0.01)
    order = lambda prefer: [m.name for m in sorted([cheap, unmeasured, quick], key=lambda m: m.ranks_after({"prefer": prefer}))]  # noqa: E731
    assert order("fastest") == ["quick", "cheap", "unmeasured"]
    assert order("cheapest") == ["unmeasured", "cheap", "quick"]


# ─────────────────────────────────────────────────────── 96 §A6: the voice plan


def test_the_desks_voice_plan_is_what_it_wrote() -> None:
    from pact_adapters.voice import plan_for

    doc = shown(TREE)
    plan = plan_for(doc, "front-desk", resolve.load_catalogue(workspace=TREE))
    assert plan is not None
    assert (plan.pipeline, plan.hears_with, plan.thinks_with, plan.speaks_with) == (
        "transcribe-think-speak", "whisper-large-v3", "qwen2.5-vl-7b-instruct", "kokoro-82m",
    )
    assert (plan.speaks_as, plan.duplex, plan.keeps_the_audio) == ("af_heart", False, "no")
    assert plan.turn_ends_after == pytest.approx(0.7)
    assert plan.may_be_interrupted


def test_pact_picks_one_model_that_listens_while_it_speaks_or_says_why_not() -> None:
    from pact_adapters.voice import plan_for

    doc = shown(TREE)
    voice = doc["agents"]["front-desk"]["voice"]
    for line in ("pipeline", "hears-with", "speaks-with", "speaks-as"):
        voice.pop(line)
    voice["talking"] = "both-at-once"
    catalogue = resolve.load_catalogue(workspace=TREE)
    plan = plan_for(doc, "front-desk", catalogue)
    assert plan is not None and plan.pipeline == "" and "listens" in plan.why

    duplex = resolve.ModelEntry(
        name="omni-local", tier="mid", cost=0.0,
        capabilities=frozenset({"audio_in", "audio_out"}), served_locally=True,
    )
    rows = {"omni-local": {"capabilities": {"sessions": ["duplex"]}}}
    richer = resolve.Catalogue(entries=catalogue.entries + (duplex,), default=catalogue.default)
    plan = plan_for(doc, "front-desk", richer, rows=rows)
    assert plan is not None
    assert (plan.pipeline, plan.thinks_with, plan.duplex) == ("one-speech-model", "omni-local", True)
    assert "PACT picked it" in plan.why


# ──────────────────────────────── 96 §A2, §A6: the lines a host binds against


def test_each_row_carries_its_voices_languages_sessions_and_dimensions() -> None:
    by_name = {e.name: e for e in resolve.load_catalogue(workspace=TREE).entries}
    assert by_name["whisper-large-v3"].languages == ("en", "hi")
    assert by_name["kokoro-82m"].voices == ("af_heart", "bm_george")
    assert by_name["kokoro-82m"].languages == ("en",)
    assert by_name["nomic-embed-text"].dimensions == 768
    assert by_name["qwen2.5-vl-7b-instruct"].sessions == frozenset({"turns"})
    # A line the row leaves out is not said, never a guess.
    assert by_name["bge-reranker-v2-m3"].voices == () and by_name["bge-reranker-v2-m3"].dimensions is None


def test_a_bound_model_is_held_to_the_voice_plan_as_the_loader_holds_a_named_one() -> None:
    from pact_adapters.voice import plan_for

    by_name = {e.name: e for e in resolve.load_catalogue(workspace=TREE).entries}
    plan = plan_for(shown(TREE), "front-desk", resolve.load_catalogue(workspace=TREE))
    assert plan is not None and plan.languages == ("en-GB",)
    # The desk's own models fit: `en` covers `en-GB`, and kokoro has `af_heart`.
    assert by_name["whisper-large-v3"].fits_voice(plan, "hears") == (True, "")
    assert by_name["kokoro-82m"].fits_voice(plan, "speaks") == (True, "")
    # A speaker without the voice, a hearer without the language, a one-model plan without duplex.
    hoarse = dataclasses.replace(by_name["kokoro-82m"], voices=("bm_george",))
    assert hoarse.fits_voice(plan, "speaks") == (False, "has no voice named 'af_heart' (its voices: bm_george)")
    assert hoarse.fits_voice(plan, "hears") == (True, ""), "a voice is the speaker's alone"
    hindi = dataclasses.replace(plan, languages=("hi",))
    assert by_name["kokoro-82m"].fits_voice(hindi, "speaks") == (False, "does not handle 'hi' (it handles: en)")
    assert by_name["whisper-large-v3"].fits_voice(hindi, "hears") == (True, "")
    both = dataclasses.replace(plan, duplex=True, speaks_as="")
    turns = by_name["qwen2.5-vl-7b-instruct"]
    assert turns.fits_voice(both, "both") == (False, "cannot listen while it speaks (its row has no `sessions: [duplex]`)")
    assert dataclasses.replace(turns, sessions=frozenset({"duplex"})).fits_voice(both, "both") == (True, "")


def test_a_duplex_row_is_picked_from_its_own_entry_with_no_raw_rows() -> None:
    from pact_adapters.voice import plan_for

    doc = shown(TREE)
    voice = doc["agents"]["front-desk"]["voice"]
    for line in ("pipeline", "hears-with", "speaks-with", "speaks-as"):
        voice.pop(line)
    voice["talking"] = "both-at-once"
    catalogue = resolve.load_catalogue(workspace=TREE)
    duplex = resolve.ModelEntry(
        name="omni-local", tier="mid", cost=0.0, capabilities=frozenset({"audio_in", "audio_out"}),
        served_locally=True, sessions=frozenset({"duplex"}),
    )
    richer = resolve.Catalogue(entries=catalogue.entries + (duplex,), default=catalogue.default)
    plan = plan_for(doc, "front-desk", richer)
    assert plan is not None and (plan.pipeline, plan.thinks_with) == ("one-speech-model", "omni-local")


def test_a_set_of_documents_names_its_embedder_and_its_reranker() -> None:
    """96 §A7: `embedded-by:` and `reranked-by:` reach the runtime that indexes the set."""
    doc = shown(TREE)
    doc["agents"]["front-desk"]["uses"] = ["acme-policies"]  # the set itself, not its interface
    spec = AgentSpec.from_document(doc, "front-desk", TREE)
    (policies,) = [k for k in spec.knowledge if k.name == "acme-policies"]
    assert (policies.embedded_by, policies.reranked_by) == ("nomic-embed-text", "bge-reranker-v2-m3")
