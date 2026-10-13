"""`served-by.region`: a catalogue row says the region each runtime serves its weights in.

A workflow's `data-stays-in:` names a region, and a runtime is told which models it may run there
only if the catalogue can say where a model is served, and by which runtime: each region is kept
with its entry's endpoint, so a call is held to the runtime the host binds, not to whichever
runtime of the row is in the region. A row read without the line is served in no region, never in
every one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.resolve import load_catalogue  # noqa: E402

ROWS = """\
models:
  baa-coder:
    description: A model the hospital's BAA covers, served in two of its regions.
    served-by:
      - { runtime: vllm, endpoint: "https://llm.us-east.example.org/v1", region: us-baa-region }
      - { runtime: vllm, endpoint: "https://llm.us-west.example.org/v1", region: us-baa-west }
  anywhere-coder:
    description: A model served with no region named.
    served-by:
      - { runtime: ollama, endpoint: local }
"""


def test_a_row_names_every_region_its_runtimes_serve_it_in(tmp_path: Path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models/catalog.yaml").write_text(ROWS)
    catalogue = load_catalogue(workspace=tmp_path)
    assert catalogue.get("baa-coder").regions == frozenset(
        {
            ("https://llm.us-east.example.org/v1", "us-baa-region"),
            ("https://llm.us-west.example.org/v1", "us-baa-west"),
        }
    ), "each region with the endpoint that serves it there"
    assert catalogue.get("anywhere-coder").regions == frozenset(), "no region named is no region"
