"""Law 8 for a plugin (D29 under docs/97-PRIMITIVES.md §4): a learning cycle
that proposes changing which plugins an agent is loaded with is held to the
checker the author's own tree is held to, and only a change that passes it is
held for a person. Nobody is asked to approve a tree that does not load."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.checking import check_agent_field  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import Learner, Proposal  # noqa: E402
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DESK = REPO / "examples" / "plugin-desk"
AGENT = "research-desk"

#: A second plugin the workspace defines, so a proposal has one to add.
CRM = {
    "description": "The customer-records client the desk's runtime loads.",
    "package": "npm:@acme/crm-tools",
    "version": "^1.4.0",
    "if-it-cannot-be-loaded": "run-without-it",
}


def _document() -> dict:
    doc = copy.deepcopy(shown(DESK))
    doc.setdefault("plugins", {})["crm-tools"] = CRM
    return doc


def _learner(doc: dict) -> Learner:
    spec = AgentSpec.from_document(doc, AGENT, source=DESK)
    return Learner.from_document(doc, spec, tools={})


def _never_scored(spec):  # a scoring run would reach here; it must not
    raise AssertionError("scored a change no cycle can apply")


def test_the_field_is_written_into_the_document_and_checked() -> None:
    doc = _document()
    assert check_agent_field(doc, AGENT, "plugins", ["web-search", "crm-tools"]) == []
    refused = check_agent_field(doc, AGENT, "plugins", ["web-search", "no-such-plugin"])
    assert refused and any("no-such-plugin" in r for r in refused), refused


def test_a_plugin_the_workspace_defines_passes_the_checker_and_is_held_for_a_person() -> None:
    learner = _learner(_document())
    out = learner.cycle(Proposal("plugins", "- web-search", "- web-search\n- crm-tools"), _never_scored)
    assert not out.applied
    assert out.held, out.reason
    assert out.reason.startswith("held for review"), out.reason
    assert learner.unchecked is None or "plugins" not in learner.unchecked


def test_a_plugin_nothing_defines_is_refused_in_the_checkers_words_and_never_held() -> None:
    learner = _learner(_document())
    out = learner.cycle(Proposal("plugins", "- web-search", "- web-search\n- no-such-plugin"), _never_scored)
    assert not out.applied
    assert not out.held, out.reason
    assert "does not pass `pact check`" in out.reason, out.reason
    assert "no-such-plugin" in out.reason, out.reason


def test_a_comma_list_is_the_same_proposal() -> None:
    learner = _learner(_document())
    out = learner.cycle(Proposal("plugins", "web-search", "web-search, no-such-plugin"), _never_scored)
    assert not out.held and "no-such-plugin" in out.reason, out.reason
    out = learner.cycle(Proposal("plugins", "web-search", "web-search, crm-tools"), _never_scored)
    assert out.held, out.reason
