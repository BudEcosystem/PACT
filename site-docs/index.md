# PACT

**A portable contract for AI agents.** An agent is a folder of YAML and Markdown.
The same folder runs on seven frameworks and two language runtimes and produces
the same trace.

```bash
cargo run -p pact-cli -- check examples/refund-desk
```

```
OK — examples/refund-desk loaded cleanly (498 settings).
```

That example is a supervisor agent, two specialists, MCP tools, a written refund
policy, an eval suite and a learning policy — **and no code you have to write**. The one Python file in the tree is a
six-line helper the refund policy carries as a payload; nothing in PACT
requires it, and deleting it leaves a working agent.

---

## Three questions, in order

<div class="grid cards" markdown>

- **[Why does this exist?](concepts/why.md)**
  Agents don't port today because the industry models them as *programs*, and
  programs don't translate.

- **[How does it work?](concepts/how.md)**
  A contract about behaviour, a plural space of strategies, and a harness that
  owns the loop so no framework does.

- **[What do you write?](concepts/what.md)**
  Files. One rule — *a directory is a field; a field may be a directory* —
  and 54 kinds you never have to memorise.

</div>

---

## What is actually true today

Every number on this site was produced by running a command against this
repository. Where something is unbuilt, [Gaps and blockers](status/gaps.md) says
so plainly rather than leaving it to be discovered.

| | |
|---|---|
| Tests | **3,811** — 1263 Rust, 2548 adapter |
| Schema kinds | **54** |
| Framework targets | **7**, over 2 runtimes |
| Eve capabilities accounted for | **101 of 101** |
| Worked example | 43 files, 498 settings, 1 payload script |

!!! note "How to check any claim on this site"
    Every page cites the command or the `file:line` behind it. If a claim has no
    citation, treat it as unverified and tell us — this project has a history of
    documents describing a system more complete than the code, and the whole
    point of citing is that you don't have to take our word for it.

---

## Where to go next

- **New here?** [Why PACT exists](concepts/why.md) → [Your first agent](guide/first-agent.md)
- **Evaluating it?** [What is true today](status/verified.md) and
  [Gaps and blockers](status/gaps.md), in that order
- **Comparing with Vercel Eve?** [Compared to Eve](status/eve.md) — a measured
  comparison, including where Eve is better
- **Building on it?** [The 54 kinds](reference/kinds.md) and
  [Adapters](reference/adapters.md)

---

## Building this site

```bash
uv tool install --with mkdocs-material mkdocs
mkdocs serve       # http://127.0.0.1:8000
mkdocs build       # → site/
```

The numbers on these pages are held by a test
(`adapters/python/tests/test_the_documentation_site_tells_the_truth.py`). Change
a count in the docs without changing the code and the suite fails, naming what
to write instead.
