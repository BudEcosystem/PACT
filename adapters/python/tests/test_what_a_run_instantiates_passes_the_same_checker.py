"""Law 8 at the moment of instantiation (97 §4, law 8): a `narrowed-new`
helper, a skill a run wrote and a `run-code` snippet are each put in front of
the checker the author's tree is held to, as the document they would make,
before they can be asked."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.checking import (  # noqa: E402
    NotNarrower,
    Uncheckable,
    check_document,
    literal,
    with_helper,
    with_program,
    with_skill,
)
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PHASES = REPO / "examples" / "kernel" / "phases"


def test_a_helper_described_on_the_spot_is_its_starter_told_something_else() -> None:
    doc = shown(PHASES)
    out = with_helper(doc, "builder", "Check the {{ order }} part.", description="Checks one part")
    starter = {k: v for k, v in doc["agents"]["builder"].items() if k != "name"}
    assert out["agents"]["builder-helper"] == {
        **starter,
        "description": "Checks one part",
        "instructions": "Check the \\{{ order }} part.",
    }
    assert check_document(out) == []
    assert "builder-helper" not in doc["agents"], "the starter's document is not changed"


def test_a_helper_may_be_narrower_than_its_starter_and_never_wider() -> None:
    doc = shown(PHASES)
    has = list(doc["agents"]["builder"].get("uses") or [])
    narrower = with_helper(doc, "builder", "Do one step.", uses=has[:1])
    assert narrower["agents"]["builder-helper"]["uses"] == has[:1]
    assert check_document(narrower) == []
    with pytest.raises(NotNarrower, match="a narrowed agent may use only what 'builder' uses"):
        with_helper(doc, "builder", "Pay out.", uses=[*has, "payments"])


def test_a_second_helper_takes_the_next_free_key() -> None:
    doc = shown(PHASES)
    twice = with_helper(with_helper(doc, "builder", "One."), "builder", "Two.")
    assert twice["agents"]["builder-helper-2"]["instructions"] == "Two."


def test_a_skill_a_run_wrote_is_checked_and_one_that_says_nothing_is_refused() -> None:
    doc = shown(PHASES)
    out = with_skill(doc, "builder", "refund-note", "Writes a refund note.", "Two lines.", use_when="a refund is decided")
    assert out["skills"]["refund-note"] == {
        "name": "refund-note", "description": "Writes a refund note.", "use-when": "a refund is decided", "content": "Two lines.",
    }
    assert check_document(out) == []
    refused = check_document(with_skill(doc, "builder", "blank", " ", "x"))
    assert any("description" in line for line in refused), refused


def test_a_snippet_is_a_program_with_the_runs_own_ceiling() -> None:
    doc = shown(PHASES)
    out = with_program(doc, "python", "print(1)", description="Adds the totals.", runs_for_at_most_ms=20_000)
    assert out["programs"]["run-code-d287bb7f9d15"] == {
        "description": "Adds the totals.", "engine": "python", "determinism": "nondeterministic",
        "fuel": {"runs-for-at-most": "20000ms", "when-it-runs-out": "stop-and-say-so"},
    }
    assert check_document(out) == []
    with pytest.raises(Uncheckable, match="no engine"):
        with_program(doc, "ruby", "p 1")


def test_words_a_model_wrote_are_read_literally_in_either_template_language() -> None:
    assert literal("a {{ b }} and \\{{ c }}", {}) == "a \\{{ b }} and \\{{ c }}"
    jinja = {"template-language": "jinja"}
    assert literal("plain words", jinja) == "plain words"
    assert literal("x {{ y }} {% endraw %} z", jinja) == (
        "{% raw %}x {{ y }} {% endraw %}{{ '{% endraw %}' }}{% raw %} z{% endraw %}"
    )
