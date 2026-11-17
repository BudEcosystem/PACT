"""A copied catalogue row records which version of the distribution's row it copied.

`benchmarks.record` copies the distribution's row before adding a figure, and
writes `copied-from.digest` beside it. The digest is taken over the JSON
`pact show` prints, so it is the one the checker computes
(`crates/pact-loader/src/copies.rs`): `spec/copied-rows.yaml` holds both
runtimes to the same digests, and `pact check` stays quiet on a fresh copy.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from pact_adapters import benchmarks
from pact_adapters.loader import pact_binary

REPO = Path(__file__).resolve().parents[3]
TABLE = yaml.safe_load((REPO / "spec" / "copied-rows.yaml").read_text(encoding="utf-8"))
BINARY = pact_binary()
needs_binary = pytest.mark.skipif(BINARY is None, reason="no `pact` binary is built here")


def _shown_row(tmp_path: Path, row: dict) -> dict:
    (tmp_path / "models").mkdir()
    (tmp_path / "workspace.yaml").write_text("name: probe\n", encoding="utf-8")
    (tmp_path / "models" / "catalog.yaml").write_text(
        yaml.safe_dump({"version": 1, "models": {"probe": row}}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    shown = subprocess.run([str(BINARY), "show", str(tmp_path)], capture_output=True, text=True, check=True)
    return json.loads(shown.stdout)["models"]["models"]["probe"]


@needs_binary
@pytest.mark.parametrize("case", TABLE["digests"], ids=lambda c: c["because"])
def test_a_row_digests_as_the_shared_table_says(case, tmp_path):
    assert benchmarks.row_digest(_shown_row(tmp_path, case["row"])) == case["digest"]


@needs_binary
def test_recording_a_figure_writes_which_row_was_copied_and_check_is_quiet(tmp_path):
    path = benchmarks.record(tmp_path, "qwen2.5-7b-instruct", "mmlu", 70.0, source="a run on this machine")
    row = yaml.safe_load(path.read_text(encoding="utf-8"))["models"]["qwen2.5-7b-instruct"]
    shipped = benchmarks._shipped_as_shown("qwen2.5-7b-instruct")
    assert shipped is not None
    assert row["copied-from"] == {"digest": benchmarks.row_digest(shipped)}
    (tmp_path / "workspace.yaml").write_text("name: copied\n", encoding="utf-8")
    checked = subprocess.run([str(BINARY), "check", str(tmp_path)], capture_output=True, text=True)
    assert "a-copied-row-behind-the-distribution" not in checked.stdout + checked.stderr


@needs_binary
def test_a_copy_whose_digest_is_not_the_shipped_rows_is_reported(tmp_path):
    path = benchmarks.record(tmp_path, "qwen2.5-7b-instruct", "mmlu", 70.0, source="a run on this machine")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["models"]["qwen2.5-7b-instruct"]["copied-from"] = {"digest": "sha256:" + "0" * 64}
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (tmp_path / "workspace.yaml").write_text("name: copied\n", encoding="utf-8")
    checked = subprocess.run([str(BINARY), "check", str(tmp_path)], capture_output=True, text=True)
    assert "loader/a-copied-row-behind-the-distribution" in checked.stdout + checked.stderr
    assert "`benchmarks`" in checked.stdout + checked.stderr


def test_a_second_figure_does_not_copy_the_row_again(tmp_path):
    first = benchmarks.record(tmp_path, "qwen2.5-7b-instruct", "mmlu", 70.0, source="a run on this machine")
    before = yaml.safe_load(first.read_text(encoding="utf-8"))["models"]["qwen2.5-7b-instruct"].get("copied-from")
    again = benchmarks.record(tmp_path, "qwen2.5-7b-instruct", "gsm8k", 80.0, source="a run on this machine")
    assert yaml.safe_load(again.read_text(encoding="utf-8"))["models"]["qwen2.5-7b-instruct"].get("copied-from") == before
