"""Pydantic AI's own files imported into a tree, every key accounted for (02P P2, E1-E10, K3).

* **`mcp.json`** (`pydantic_ai_files.from_mcp_json`): one resource per server, the tree loads
  once it lets tools out, and nothing a server is launched with or sent (where credentials
  live) reaches a file or the report;
* **a pydantic-evals dataset** (`pydantic_evals_datasets.from_pydantic_evals`): the file is one
  pydantic-evals itself loads, and what it becomes is a suite `pact check` loads and PACT's eval
  reader reads, each case's `expect:` and rules as the evaluators said;
* **a folder of harness agents** (`pydantic_ai_files.from_agent_folder`): agent files the
  loader accepts, with what the harness ignores named;
* **no silent drop**: a reader that forgets a key's bucket is caught.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, rules_of  # noqa: E402
from pact_adapters.openapi import NotImported, write_into  # noqa: E402
from pact_adapters.pydantic_ai_files import from_agent_folder, from_mcp_json  # noqa: E402
from pact_adapters.pydantic_evals_datasets import from_pydantic_evals  # noqa: E402
from trees import pact, shown, write  # noqa: E402

PARITY = Path(__file__).resolve().parents[3] / "tests" / "parity"
SECRET = "sk-live-2f9c41ab77d3e015aa9e"


def _tree(at: Path, egress: str = "[]", **files: str) -> Path:
    return write(at, {"workspace.yaml": f"name: imported\nallow-egress: {egress}\n", **files})


def test_an_mcp_json_is_one_resource_per_server_and_no_secret_crosses(tmp_path: Path) -> None:
    config = {
        "mcpServers": {
            "orders": {"url": "https://orders.example.com/mcp", "headers": {"Authorization": f"Bearer {SECRET}"}},
            "files": {"command": "npx", "args": ["server-filesystem"], "env": {"API_KEY": SECRET}},
            "billing": {"url": f"https://billing.example.com/mcp?key={SECRET}"},
            # Zapier's hosted MCP server carries the account's secret in its path.
            "zapier": {"url": "https://mcp.zapier.com/api/mcp/s/NzE4YjQ2ZTgtY2Q0MS00Zg9kLWI2/mcp"},
            # A credential as a path parameter, a subdomain, and a short key with a known prefix.
            "params": {"url": "https://mcp.example.com/mcp;token=tok-PARAM"},
            "tenant": {"url": "https://abc123def456ghi789.mcp.example.com/sse"},
            "short": {"url": "https://example.com/mcp/sk-abcd1234"},
            # Two servers whose names are one PACT name: two files, never one overwritten.
            "my_server": {"url": "https://a.example.com/mcp"},
            "my-server": {"url": "https://b.example.com/mcp"},
        }
    }
    imported = from_mcp_json(config)
    assert imported.report.silent_drops == () and imported.report.unmapped == {}
    every_word = "".join(map(str, imported.files.values())) + imported.report.in_words()
    for secret in (SECRET, "NzE4YjQ2", "tok-PARAM", "abc123def456ghi789", "sk-abcd1234"):
        assert secret not in every_word, f"a credential crossed: {secret}"
    bodies = {f: yaml.safe_load(t) for f, t in imported.files.items()}
    assert bodies["resources/orders.yaml"]["endpoint"] == "https://orders.example.com/mcp"
    for server in ("files", "billing", "zapier", "params", "tenant", "short"):
        assert bodies[f"resources/{server}.yaml"]["endpoint"] == f"host/{server}"
    assert bodies["resources/my-server.yaml"]["endpoint"] == "https://a.example.com/mcp"
    assert bodies["resources/my-server-2.yaml"]["endpoint"] == "https://b.example.com/mcp"
    root = _tree(tmp_path / "tree", "[tools]")
    write_into(root, imported)
    out = pact("check", str(root))
    assert out.returncode == 0, out.stdout + out.stderr
    assert any("connect: orders" in line for line in imported.report.still_to_write)


def test_a_malformed_mcp_json_is_refused_without_quoting_it(tmp_path: Path) -> None:
    """A parser's message quotes the line it stopped at, and an `mcp.json`'s lines hold tokens:
    the refusal says what is wrong and where, never what is written there."""
    from pact_adapters.importing import read_files

    bad = tmp_path / "mcp.json"
    bad.write_text('{"mcpServers": {"a": {"url": "https://a.example.com", "headers": '
                   f'{{"Authorization": "Bearer {SECRET}"}}\t,}}}}}}\n', encoding="utf-8")
    with pytest.raises(NotImported, match="line 1, column") as refused:
        read_files("mcp-json", bad)
    assert SECRET not in str(refused.value)


def test_an_mcp_json_without_servers_is_refused() -> None:
    with pytest.raises(NotImported, match="no `mcpServers:`"):
        from_mcp_json({"servers": {}})


def test_a_dataset_is_one_pydantic_evals_loads_and_its_suite_is_one_pact_reads(tmp_path: Path) -> None:
    pydantic_evals = pytest.importorskip("pydantic_evals")
    source = PARITY / "E2" / "dataset.yaml"
    pydantic_evals.Dataset[str, str, dict].from_file(source)  # the fixture is pydantic-evals' own format
    imported = from_pydantic_evals(yaml.safe_load(source.read_text()))
    root = _tree(
        tmp_path / "tree",
        **{"agents/desk.yaml": "description: Decides refunds.\ninstructions: Approve or decline.\nevals: evals\n"},
    )
    write_into(root, imported)
    out = pact("check", str(root))
    assert out.returncode == 0, out.stdout + out.stderr
    document = shown(root)
    (case,) = Case.from_document(document)
    assert case.expect == {"answer": "approved"}
    assert [(r.kind, r.values) for r in case.must_also] == [("must-say-one-of", ("approved",))]
    assert [(r.kind, r.values) for r in rules_of(document)] == [("must-contain", ("refund",))]


def test_a_max_duration_pydantic_evals_wrote_from_a_timedelta_is_read(tmp_path: Path) -> None:
    """`MaxDuration(seconds=timedelta(...))` is saved as an ISO 8601 duration (`PT2S`): it is the
    `limits:` line of two seconds, and a `MaxDuration` that is no duration is refused, said."""
    pydantic_evals = pytest.importorskip("pydantic_evals")
    from datetime import timedelta

    from pydantic_evals.evaluators import MaxDuration

    source = tmp_path / "dataset.yaml"
    pydantic_evals.Dataset[str, str, dict](
        name="quick", cases=[pydantic_evals.Case(name="hi", inputs="hi")],
        evaluators=[MaxDuration(seconds=timedelta(seconds=2))],
    ).to_file(source)
    assert "PT2S" in source.read_text()
    owed = from_pydantic_evals(yaml.safe_load(source.read_text())).report.still_to_write
    assert any("finishes-within: 2s" in line for line in owed), owed
    with pytest.raises(NotImported, match="`MaxDuration: None` is not a duration"):
        from_pydantic_evals({"cases": [], "evaluators": ["MaxDuration"]})


def test_a_judge_is_graded_by_its_models_catalogue_row() -> None:
    suite = yaml.safe_load(from_pydantic_evals(yaml.safe_load((PARITY / "E6" / "dataset.yaml").read_text())).files["evals/suite.yaml"])
    assert suite["graded-by"] == "claude-haiku-4-5"
    assert suite["rules"] == [{"judged": "The answer is one sentence and names the 30-day window."}]


def test_a_harness_agent_folder_is_agent_files_the_loader_accepts(tmp_path: Path) -> None:
    imported = from_agent_folder(PARITY / "K3" / "agents")
    assert imported.report.silent_drops == ()
    root = _tree(tmp_path / "tree")
    write_into(root, imported)
    out = pact("check", str(root))
    assert out.returncode == 0, out.stdout + out.stderr
    agents = shown(root)["agents"]
    assert agents["researcher"]["instructions"] == "You research topics. Report your findings, each with a source."
    assert agents["reviewer"]["description"] == "Reviews code for bugs"
    assert any("`team:`" in line and "researcher" in line for line in imported.report.still_to_write)


def test_a_link_or_a_hidden_file_in_an_agent_folder_is_never_read(tmp_path: Path) -> None:
    """A folder read through a confined door stays inside it: a definition that is a link (to
    `~/.aws/credentials`, say) and a hidden file are named, and their words cross nowhere."""
    outside = tmp_path / "outside.md"
    outside.write_text("TOP SECRET\n", encoding="utf-8")
    folder = write(tmp_path / "agents", {"helper.md": "---\nname: helper\n---\nHelp.\n", ".spy.md": "TOP SECRET\n"})
    (folder / "spy.md").symlink_to(outside)
    imported = from_agent_folder(folder)
    assert set(imported.files) == {"agents/helper.yaml"}
    assert "TOP SECRET" not in "".join(imported.files.values())
    assert {"spy.md", ".spy.md"} <= set(imported.report.not_portable) and imported.report.silent_drops == ()


def test_a_definition_that_is_not_utf8_is_refused_said(tmp_path: Path) -> None:
    folder = tmp_path / "agents"
    folder.mkdir()
    (folder / "a.md").write_bytes("---\nname: a\n---\nHi\n".encode("utf-16"))
    with pytest.raises(NotImported, match="a.md is not UTF-8 text. Fix: save it as UTF-8"):
        from_agent_folder(folder)


@pytest.mark.parametrize("door", ["mcp", "evals", "agents"])
def test_a_key_the_reader_forgets_is_a_silent_drop(door: str) -> None:
    """The control: each reader's report is computed from the source, so a bucket it forgets to
    fill shows up as left out."""
    if door == "mcp":
        report = from_mcp_json(json.loads((PARITY / "P2" / "mcp.json").read_text())).report
    elif door == "evals":
        report = from_pydantic_evals(yaml.safe_load((PARITY / "E1" / "dataset.yaml").read_text())).report
    else:
        report = from_agent_folder(PARITY / "K3" / "agents").report
    assert report.silent_drops == ()
    forgotten = sorted(report.mapped)[0]
    del report.mapped[forgotten]
    assert report.silent_drops == (forgotten,)


def test_pact_import_and_pact_pydantic_ai_are_the_doors_on_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`pact-import --as mcp-json|pydantic-evals|agent-folder|skills [--out DIR]` and
    `pact-pydantic-ai PATH AGENT --skills DIR`: the same importers and exporter, for a PACT user
    with no runtime of their own."""
    from pact_adapters.importing import main as pact_import
    from pact_adapters.pydantic_ai_interop import main as pact_pydantic_ai

    root = _tree(tmp_path / "tree", "[tools]")
    for kind, source in (("mcp-json", "P2/mcp.json"), ("pydantic-evals", "E1/dataset.yaml"), ("agent-folder", "K3/agents")):
        assert pact_import([str(PARITY / source), "--as", kind, "--out", str(root)]) == 0, capsys.readouterr().err
    assert pact_import([str(PARITY / "X5" / "skills"), "--as", "skills"]) == 0
    assert "--- # skills/refund-policy/SKILL.md" in capsys.readouterr().out
    assert {"resources", "evals", "agents"} <= {p.name for p in root.iterdir()}

    desk = Path(__file__).resolve().parents[3] / "examples" / "refund-desk"
    assert pact_pydantic_ai([str(desk), "refund-desk", "--skills", str(tmp_path / "skills")]) == 0
    assert (tmp_path / "skills" / "refund-policy" / "SKILL.md").is_file()
    assert "Wrote 3 file(s)" in capsys.readouterr().out
