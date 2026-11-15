# a-desk-that-needs-a-plugin

A desk that cannot do its job without the CRM plugin its runtime loads, and says
so on the plugin's own line by leaving `if-it-cannot-be-loaded:` out.

```
workspace.yaml
agents/desk/agent.yaml          plugins: [crm-tools]
agents/desk/instructions.md
plugins/crm-tools.yaml          package: pypi:acme-crm-tools, version: ">=1.4,<2"
```

## What this tree is for

`refuse-to-start` is the default (D29), and it is the one that changes where an
agent can run at all: on a runtime that cannot load `pypi:` packages this desk
never starts. That is a portability fact, so `pact check` says it before anybody
runs anything — as a note, because it is what the author meant and a shipped
tree that means it must still pass `--deny-warnings`:

```bash
cargo run -p pact-cli -- check tests/trees/a-desk-that-needs-a-plugin
```

```
note: 'desk' runs only where `pypi:acme-crm-tools` can be loaded: 'crm-tools' says
      `refuse-to-start`, so on a runtime that cannot load it the agent stops before
      the first step.
  rule: loader/plugin-runs-only-where-loaded
OK — a-desk-that-needs-a-plugin loaded cleanly (18 settings).
```

`pact discover` publishes the same fact per agent — `plugins: [{name, package,
version, if-it-cannot-be-loaded: refuse-to-start}]` — so a runtime can decline
the agent before it takes it.

## And the run

The reference harness loads no plugin, and neither does the second port, so both
end the turn before a model is called:

```
halted: plugins-not-loaded
output: This agent cannot start: it needs 'crm-tools' (`pypi:acme-crm-tools`,
        versions `>=1.4,<2`), and nothing running it loaded it. fix: run it where a
        runtime loads `pypi:` packages, or write `if-it-cannot-be-loaded:
        run-without-it` in the plugin's file under `plugins/` if the agent can do
        its job without it.
```

A host that does load the package says so with `run(loaded_plugins={"crm-tools":
"1.4.2"})`, and the desk runs. Held by
`adapters/python/tests/test_a_plugin_nobody_loaded_stops_the_run_before_it_starts.py`.

The settings carry the CRM key as `{by-reference: host/crm-key}`. Writing the key
itself there is `loader/plugin-secret-written-in-the-file`.
