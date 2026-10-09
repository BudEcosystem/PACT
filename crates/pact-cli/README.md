# pact-loader

The PACT loader, `pact`, as a Python wheel. It checks a PACT tree (a folder of YAML and
Markdown that describes agents, tools, approvals and limits) and prints the one document every
runtime reads.

```bash
pip install pact-loader     # or: pip install pact-adapters, which depends on it
pact check path/to/tree
pact show path/to/tree
```

The wheel carries one native executable and no Python code. Wheels are built for Linux
(manylinux 2.28) on x86_64 and aarch64; on any other platform `pip` builds it from the source
distribution, which needs a Rust toolchain (`rustup`, stable).

`pact` never runs the tree's code. Running a tree is a runtime's job: the harness in
`pact-adapters`, or Bud Agent Flow (`budflow-core`) on Pydantic AI.
