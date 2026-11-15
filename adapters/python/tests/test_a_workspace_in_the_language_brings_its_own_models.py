"""A workspace written in the PACT language brings its own model rows (docs/99 §4.4).

`resolve.load_catalogue(workspace=…)` is the override layer: what an author on
an air-gapped machine writes to add the one model this distribution has never
heard of. In a folder that is `models/catalog.yaml`. In a `.pact` file it is a
`models` block, and `pact check` reads it from the document — which is why a
`voice:` naming such a model passes the check.

Nothing here read it. The resolver opened `<root>/models/catalog.yaml` from the
disk and found no such file, so the workspace's own transcriber and speaker were
held by the checker and unknown to everything that binds, prices or sizes a
model. Handed the `.pact` file itself, it parsed the WORKSPACE as a catalogue.

Found while Bud Agent Flow was being held to docs/99: its model binding goes
through this function, and asked whether a `.pact` file can declare a row.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters import resolve  # noqa: E402
from pact_adapters.voice import plan_for  # noqa: E402
from trees import PACT_BIN, shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
#: A desk that hears with one model and speaks with another, both rows of its
#: own `models/catalog.yaml`, neither in the catalogue PACT ships.
FOLDER = REPO / "tests" / "trees" / "a-desk-that-listens-reads-and-chooses"
OWN = ("whisper-large-v3", "kokoro-82m")


def as_one_file(tmp_path: Path) -> Path:
    """`FOLDER`, written in the language: one `.pact` file at the top of a
    folder that still holds the documents, which stay files."""
    root = tmp_path / "desk"
    (root / "knowledge" / "acme-policies").mkdir(parents=True)
    shutil.copytree(
        FOLDER / "knowledge" / "acme-policies" / "documents",
        root / "knowledge" / "acme-policies" / "documents",
    )
    printed = subprocess.run([str(PACT_BIN), "write", str(FOLDER)], capture_output=True, text=True, check=True)
    (root / "desk.pact").write_text(printed.stdout)
    assert not (root / "models").exists(), "the rows are in the .pact file, and nowhere on disk"
    assert shown(root) == shown(FOLDER), "the same workspace, written the other way"
    return root


def test_the_rows_this_is_about_are_the_workspaces_own() -> None:
    shipped = {e.name for e in resolve.load_catalogue().entries}
    assert not set(OWN) & shipped, "these have to be rows only the workspace brings"
    assert set(OWN) <= {e.name for e in resolve.load_catalogue(workspace=FOLDER).entries}


def test_a_folder_holding_a_pact_file_brings_the_rows_written_in_it(tmp_path: Path) -> None:
    root = as_one_file(tmp_path)
    from_file = {e.name: e for e in resolve.load_catalogue(workspace=root).entries}
    from_folder = {e.name: e for e in resolve.load_catalogue(workspace=FOLDER).entries}
    assert set(OWN) <= set(from_file)
    # Row for row what the folder gives: the same voices, languages and prices.
    for name in from_folder:
        assert from_file[name] == from_folder[name], name
    assert from_file["kokoro-82m"].voices == ("af_heart", "bm_george")


def test_the_voice_plan_is_the_one_the_folder_gets(tmp_path: Path) -> None:
    root = as_one_file(tmp_path)
    doc = shown(root)
    plan = plan_for(doc, "front-desk", resolve.load_catalogue(workspace=root))
    assert plan == plan_for(shown(FOLDER), "front-desk", resolve.load_catalogue(workspace=FOLDER))
    assert (plan.hears_with, plan.speaks_with) == OWN, plan


ALONE = """\
workspace "Team"
  description: One agent on a model this machine serves.

models
  version: 1
  models:
    house-model:
      served-by: [{runtime: ollama, endpoint: local}]
      capabilities:
        context-window:
          value: 8192
          provenance: {source: measured on this machine}

agent helper
  description: Helps.
  model: house-model
  instructions: Help.
"""


def test_a_pact_file_on_its_own_is_read_and_is_not_taken_for_a_catalogue(tmp_path: Path) -> None:
    one = tmp_path / "team.pact"
    one.write_text(ALONE)
    checked = subprocess.run([str(PACT_BIN), "check", str(one)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    catalogue = resolve.load_catalogue(workspace=one)
    assert catalogue.errors == (), catalogue.errors
    assert catalogue.window_of("house-model") == 8192
    # And every row PACT ships is still there: the workspace adds, it does not replace.
    assert {e.name for e in resolve.load_catalogue().entries} <= {e.name for e in catalogue.entries}


def test_a_folder_of_yaml_is_read_from_its_file_as_it_always_was() -> None:
    # No `.pact` file, so no loader is asked: the disk is the fast path it was.
    assert resolve._written_in_the_language(FOLDER) == ()
    assert set(OWN) <= {e.name for e in resolve.load_catalogue(workspace=FOLDER).entries}


def test_a_runtime_area_is_not_a_file_written_in_the_language(tmp_path: Path) -> None:
    root = tmp_path / "w"
    (root / ".pact" / "learning").mkdir(parents=True)
    assert resolve._written_in_the_language(root) == ()
