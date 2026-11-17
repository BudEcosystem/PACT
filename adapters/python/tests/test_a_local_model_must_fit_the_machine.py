"""A catalogue row's `size:` and `requires:` mean one thing in every runtime.

`spec/hardware-fit.yaml` is the table; the Rust checker reads its value
sections and this file reads all of it, so a figure the checker accepts is a
figure the resolver reads, and a machine that cannot hold a model served on it
alone leaves that model out with the same sentence everywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pact_adapters import machine as m
from pact_adapters.resolve import ModelEntry, _hardware, _served_locally, load_catalogue, needs_of

TABLE = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "spec" / "hardware-fit.yaml").read_text(encoding="utf-8")
)


def _machine(written: dict) -> m.Machine:
    accelerator = written.get("accelerator-memory")
    return m.Machine(
        memory_bytes=m.bytes_of(written["memory"]) if "memory" in written else None,
        accelerator_memory_bytes=0 if accelerator == "none" else (m.bytes_of(accelerator) if accelerator else None),
    )


@pytest.mark.parametrize("row", TABLE["sizes"], ids=lambda r: r["written"])
def test_a_parameter_count_reads_as_the_table_says(row):
    want = None if row["reads"] == "unknown" else float(row["reads"])
    assert m.parameters_of(row["written"]) == want


@pytest.mark.parametrize("row", TABLE["not-sizes"], ids=lambda r: r["written"])
def test_a_parameter_count_the_table_refuses_does_not_read(row):
    assert m.parameters_of(row["written"]) is None


@pytest.mark.parametrize("row", TABLE["memories"], ids=lambda r: r["written"])
def test_a_memory_figure_reads_as_the_table_says(row):
    want = None if row["reads"] == "unknown" else int(row["reads"])
    assert m.bytes_of(row["written"]) == want


@pytest.mark.parametrize("row", TABLE["not-memories"], ids=lambda r: r["written"])
def test_a_memory_figure_the_table_refuses_does_not_read(row):
    assert m.bytes_of(row["written"]) is None


def _entry(row: dict) -> ModelEntry:
    memory = str(row["memory"])
    served = [{"runtime": "ollama", "endpoint": "local"}]
    if row.get("served-elsewhere") is True:
        served.append({"runtime": "vllm", "endpoint": "https://models.example"})
    written = {"requires": {"memory": {"value": memory}}, "served-by": served}
    if "accelerator" in row:
        written["requires"]["accelerator"] = row["accelerator"]
    return ModelEntry(name="local-model", tier="small", cost=0.0, served_locally=_served_locally(served), **_hardware(written))


@pytest.mark.parametrize("row", TABLE["fits"], ids=lambda r: f"{r['memory']}-{r['because']}")
def test_a_machine_holds_a_model_served_on_it_as_the_table_says(row):
    fits, why = _entry(row).fits_machine(_machine(row["machine"]))
    assert fits is row["fits"], row["because"]
    if "says" in row:
        assert why == row["says"]
    if fits:
        assert why == ""


def test_satisfies_leaves_out_a_local_model_the_machine_cannot_hold(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "catalog.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "models": {
                    "big-local": {
                        "tier": "mid",
                        "served-by": [{"runtime": "ollama", "endpoint": "local"}],
                        "size": {"value": "32B", "provenance": {"source": "the model card"}},
                        "requires": {"memory": {"value": "20 GB", "provenance": {"source": "measured with the runtime"}}},
                        "cost": {"input-per-mtok": "0 USD", "output-per-mtok": "0 USD"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    row = load_catalogue(workspace=tmp_path).get("big-local")
    assert row is not None and row.parameters == 32e9 and row.memory_bytes == 20 * 10**9
    needs = needs_of({"agents": {"a": {"instructions": "x"}}}, "a")
    assert row.satisfies(needs) == (True, "")
    assert row.satisfies(needs, m.Machine(memory_bytes=8 * 10**9)) == (
        False,
        "needs 20 GB of memory, and this machine has 8 GB",
    )
    assert row.satisfies(needs, m.Machine(memory_bytes=64 * 10**9)) == (True, "")


def test_this_machine_reports_its_memory_and_not_its_accelerator():
    here = m.this_machine()
    assert here.accelerator_memory_bytes is None
    assert here.memory_bytes is None or here.memory_bytes > 0
