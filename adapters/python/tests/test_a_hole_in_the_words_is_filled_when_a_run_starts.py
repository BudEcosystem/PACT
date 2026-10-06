"""02P §3.2 A1 — run-time holes in `instructions:` and `description:`.

`{{run-inputs.<n>}}` and `{{remembers.<n>}}` are filled by the host when a run
starts. Three halves, each held here:

* the loader refuses a hole naming something the agent does not declare
  (`crates/pact-loader/src/holes.rs`), measured through the real binary;
* `ir.AgentSpec.holes` carries every hole a loaded document has, so a host
  knows what it must supply before it builds a prompt;
* PACT's own harness fills them before the model reads a word;
* `holes.fill` is strict — an unfilled hole is an error, never literal braces
  and never an empty string in front of a model — and finds exactly the holes
  the loader's scan finds, so nothing the checker skipped is filled at run time;
* braces a model is meant to read stay braces: a name in neither namespace is
  text (with a warning from the checker), and `\\{{` is the one escape;
* a variant's words are held and filled like the agent's own.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.holes import Hole, Unfilled, fill, holes_in  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
#: The debug build, like every other test that reads through the loader:
#: `scripts/test-all.sh` builds exactly that one, so a stale release binary
#: (which `loader.pact_binary` would prefer) can never answer for this suite.
PACT_BIN = REPO / "target" / "debug" / "pact"

AGENT = """\
description: Writes listings for {{run-inputs.brand}}
run-inputs:
  brand: text
  examples: text
remembers:
  tone:
    description: how this customer likes to be written to
    lasts: one-conversation
instructions: |
  Write in this voice: {{ run-inputs.brand }}
  Match these: {{run-inputs.examples}}, and keep {{remembers.tone}}.
  A JSON example is not a hole: {{"a": 1}}, and neither is {{#each x}}.
"""


def _tree(root: Path, agent: str) -> Path:
    (root / "agents").mkdir(parents=True)
    (root / "workspace.yaml").write_text("name: holes\nallow-egress: []\n")
    (root / "agents" / "writer.yaml").write_text(agent)
    return root


def _pact(*args: str) -> subprocess.CompletedProcess[str]:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    return subprocess.run([str(PACT_BIN), *args], capture_output=True, text=True)


def test_the_grammar_is_the_loaders() -> None:
    """The same inputs `holes.rs::the_grammar_takes_dotted_names_and_skips_everything_else` uses."""
    found = holes_in("a {{ run-inputs.x }} b {{#each}} {{\"k\": 1}} {{remembers.y}}\n{{z}}")
    # `{{z}}` names neither namespace: the loader says so, and here it is text.
    assert found == (Hole("run-inputs", "x"), Hole("remembers", "y"))
    # The loader's scan steps past `{{` only, so a triple brace is not a hole on
    # either side. A regular expression would have found one here.
    assert holes_in("{{{run-inputs.x}}}") == ()
    assert holes_in("{{run-inputs.x}} and {{run-inputs.x}}") == (Hole("run-inputs", "x"),)


def test_a_loaded_document_carries_its_holes(tmp_path: Path) -> None:
    root = _tree(tmp_path / "w", AGENT)
    checked = _pact("check", str(root))
    assert checked.returncode == 0, checked.stdout + checked.stderr
    shown = _pact("show", str(root))
    spec = AgentSpec.from_document(json.loads(shown.stdout), "writer")
    assert spec.holes == (
        Hole("run-inputs", "brand"),
        Hole("run-inputs", "examples"),
        Hole("remembers", "tone"),
    )
    assert {h.name for h in spec.holes if h.namespace == "run-inputs"} <= set(spec.run_inputs)
    assert {h.name for h in spec.holes if h.namespace == "remembers"} <= set(spec.facts.declared)
    # Carried unfilled: the values arrive with a run, not with the document.
    assert "{{ run-inputs.brand }}" in spec.instructions


@pytest.mark.parametrize(
    ("written", "rule"),
    [
        ("{{run-inputs.examples}}", "loader/no-such-run-input"),
        ("{{remembers.tone}}", "loader/no-such-remembered-fact"),
    ],
)
def test_a_hole_naming_nothing_is_refused_where_the_author_is(
    tmp_path: Path, written: str, rule: str
) -> None:
    misspelt = written.replace("}}", "x}}")
    root = _tree(tmp_path / "w", AGENT.replace(written, misspelt))
    checked = _pact("check", str(root))
    said = checked.stdout + checked.stderr
    assert checked.returncode != 0, said
    assert f"rule: {rule}" in said, said
    assert "writer.yaml:11" in said, said  # file:line of the hole itself
    assert "fix:" in said and written in said, said  # and the hole that does exist


def test_a_hole_in_neither_namespace_is_refused(tmp_path: Path) -> None:
    root = _tree(tmp_path / "w", AGENT.replace("{{ run-inputs.brand }}", "{{brand}}"))
    said = _pact("check", str(root))
    assert said.returncode != 0
    assert "rule: loader/not-a-hole" in said.stdout + said.stderr


def test_fill_puts_the_values_in_and_leaves_text_alone() -> None:
    text = "Voice: {{ run-inputs.brand }}. Keep {{remembers.tone}}. {{#each x}} {{\"a\": 1}}"
    assert fill(text, run_inputs={"brand": "Acme"}, remembers={"tone": ["dry", "short"]}) == (
        'Voice: Acme. Keep ["dry", "short"]. {{#each x}} {{"a": 1}}'
    )
    assert fill("no holes at all") == "no holes at all"


@pytest.mark.parametrize("given", [{}, {"brand": None}])
def test_an_unfilled_hole_is_an_error_and_never_braces(given: dict[str, object]) -> None:
    with pytest.raises(Unfilled) as caught:
        fill("Voice: {{run-inputs.brand}}", run_inputs=given)
    assert caught.value.hole == Hole("run-inputs", "brand")
    assert "run_inputs" in str(caught.value) and "brand" in str(caught.value)


def test_a_name_in_neither_namespace_is_text_and_never_filled() -> None:
    """`{{first_name}}` in instructions that tell a model to write a template is
    the author's own braces. It used to stop every run (`Unfilled`), with no
    way to write it; it is never filled from a value of the same name either."""
    assert fill("Greet {{first_name}}.") == "Greet {{first_name}}."
    assert fill("{{brand}}", run_inputs={"brand": "Acme"}) == "{{brand}}"


def test_a_backslash_says_the_braces_are_meant() -> None:
    """The one escape: never a hole, and sent without the backslash."""
    text = r"Tag it \{{run-inputs.brand}} for {{run-inputs.brand}}, order \{{order_id}}."
    assert holes_in(text) == (Hole("run-inputs", "brand"),)
    assert fill(text, run_inputs={"brand": "Acme"}) == (
        "Tag it {{run-inputs.brand}} for Acme, order {{order_id}}."
    )
    # Nothing to supply, and the backslash still goes.
    assert fill(r"Write \{{run-inputs.brand}}.") == "Write {{run-inputs.brand}}."


TREES = REPO / "tests" / "trees"


def _loaded(tree: str, agent: str) -> AgentSpec:
    shown = _pact("show", str(TREES / tree))
    assert shown.returncode == 0, shown.stdout + shown.stderr
    return AgentSpec.from_document(json.loads(shown.stdout), agent)


def test_braces_the_model_is_meant_to_read_reach_it_as_braces() -> None:
    """The fixture tree, through the real loader and PACT's own harness: it
    loads (one warning), the hole is filled, and both the unescaped template
    braces and the escaped ones arrive as the braces the author wrote."""
    checked = _pact("check", str(TREES / "braces-the-model-is-meant-to-read"))
    said = checked.stdout + checked.stderr
    assert checked.returncode == 0 and said.count("rule: loader/not-a-hole") == 1, said
    spec = _loaded("braces-the-model-is-meant-to-read", "mailer")
    assert spec.holes == (Hole("run-inputs", "brand"),)
    seeing = _Seeing(Script([Turn("done")]))
    asyncio.run(run(spec, seeing, "write one", {}, run_inputs={"brand": "Acme"}))
    told = seeing.systems[0]
    assert "Write an email template for Acme." in told, told
    assert "Greet the reader as {{first_name}};" in told, told
    assert "Quote their order as {{order_id}}," in told and "as {{run-inputs.brand}}." in told, told
    assert "\\" not in told, told


@pytest.mark.parametrize(
    ("tree", "rule", "times"),
    [
        ("braces-that-are-nearly-a-hole", "loader/almost-a-hole", 3),
        ("a-variant-with-a-hole-nothing-fills", "loader/no-such-run-input", 1),
        ("a-variant-with-a-hole-nothing-fills", "loader/no-such-remembered-fact", 1),
    ],
)
def test_the_checker_says_what_it_found_in_each_fixture_tree(tree: str, rule: str, times: int) -> None:
    checked = _pact("check", str(TREES / tree))
    said = checked.stdout + checked.stderr
    assert said.count(f"rule: {rule}") == times, said
    assert (checked.returncode == 0) == rule.endswith("almost-a-hole"), said


def test_a_hole_in_folded_or_quoted_words_is_reported_at_the_line_it_is_on() -> None:
    checked = _pact("check", str(TREES / "a-hole-in-folded-and-quoted-words"))
    said = checked.stdout + checked.stderr
    assert checked.returncode != 0, said
    assert "writer.yaml:6:12" in said and "writer.yaml:11:17" in said, said


def test_a_variants_holes_are_carried_and_filled_like_the_agents_own(tmp_path: Path) -> None:
    """`_variant.apply` replaced the words and kept the authored agent's holes,
    so a hole only the variant writes was one no host was told to supply."""
    from pact_adapters.resolve import strategies_of

    variants = (
        "variants:\n  toned:\n    when: a model that drifts\n"
        "    says: Match the tone in {{run-inputs.examples}}.\n"
        "  rewritten:\n    when: long instructions read badly\n"
        "    instructions: Keep {{remembers.tone}}.\n"
    )
    agent = AGENT.replace("  Match these: {{run-inputs.examples}}, and keep {{remembers.tone}}.\n", "")
    root = _tree(tmp_path / "w", agent + variants)
    checked = _pact("check", str(root))
    assert checked.returncode == 0, checked.stdout + checked.stderr
    spec = AgentSpec.from_document(json.loads(_pact("show", str(root)).stdout), "writer")
    assert spec.holes == (Hole("run-inputs", "brand"),)
    ways = strategies_of(spec)
    toned = ways["toned"](spec)
    assert toned.holes == (Hole("run-inputs", "brand"), Hole("run-inputs", "examples"))
    # `description:` is not replaced, so its hole stays beside the new words'.
    assert ways["rewritten"](spec).holes == (Hole("remembers", "tone"), Hole("run-inputs", "brand"))
    seeing = _Seeing(Script([Turn("done")]))
    asyncio.run(run(toned, seeing, "write one", {}, run_inputs={"brand": "Acme", "examples": "A, B"}))
    assert "Match the tone in A, B." in seeing.systems[0], seeing.systems[0]
    with pytest.raises(Unfilled, match="examples"):
        asyncio.run(run(toned, _Seeing(Script([Turn("done")])), "x", {}, run_inputs={"brand": "Acme"}))


class _Seeing(ReferenceTransport):
    """Keeps every system message it is handed."""

    def __init__(self, script: Script) -> None:
        super().__init__(script)
        self.systems: list[str] = []

    async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
        self.systems.append(system)
        return await super().model_call(system, history, tools)


def _spec() -> AgentSpec:
    import yaml

    return AgentSpec.from_document({"agents": {"writer": yaml.safe_load(AGENT)}}, "writer")


def test_the_harness_fills_the_holes_before_the_model_reads_them() -> None:
    seeing = _Seeing(Script([Turn("done")]))
    asyncio.run(
        run(
            _spec(), seeing, "write one", {},
            run_inputs={"brand": "Acme", "examples": "A, B"},
            remembered={"tone": "dry"},
        )
    )
    assert seeing.systems, "the model was never called"
    said = seeing.systems[0]
    assert "Write in this voice: Acme" in said and "Match these: A, B" in said, said
    assert "keep dry." in said and "{{run-inputs" not in said and "{{remembers" not in said, said


def test_the_harness_refuses_a_run_missing_a_value_a_hole_needs() -> None:
    seeing = _Seeing(Script([Turn("done")]))
    with pytest.raises(Unfilled, match="examples"):
        asyncio.run(run(_spec(), seeing, "write one", {}, run_inputs={"brand": "Acme"},
                        remembered={"tone": "dry"}))
    assert seeing.systems == [], "the model was called with a hole in its instructions"


def test_an_exported_spec_file_says_its_holes_will_reach_the_model_unfilled() -> None:
    """A spec file is read with no run. The words went out with their braces and
    the report, which exists to name every loss, said `instructions` was carried."""
    import yaml

    from pact_adapters.pydantic_ai_interop import to_pydantic_ai_spec

    written, report = to_pydantic_ai_spec({"agents": {"writer": yaml.safe_load(AGENT)}}, "writer")
    assert "{{ run-inputs.brand }}" in written["instructions"]
    assert "`{{run-inputs.brand}}`" in report.not_carried["instructions.holes"]
    assert "`{{remembers.tone}}`" in report.not_carried["instructions.holes"]
    assert "build_agent(spec, run_inputs=" in report.not_carried["description.holes"]
    plain, quiet = to_pydantic_ai_spec({"agents": {"a": {"instructions": "Help."}}}, "a")
    assert not [k for k in quiet.not_carried if k.endswith(".holes")]
