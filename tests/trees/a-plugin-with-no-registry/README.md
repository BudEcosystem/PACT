# a-plugin-with-no-registry

The CRM desk of `tests/trees/a-desk-that-needs-a-plugin/`, with one line
different: the plugin's `package:` is written without the registry in front.

```
plugins/crm-tools.yaml          package: acme-crm-tools
```

It lives here and not under `examples/` because the refusal is the behaviour
under test: every tree under `examples/` is held to `--deny-warnings`.

## Why it is refused

The word in front of the colon — `npm:`, `pypi:` — is what says which runtimes
can load the plugin at all. Without it no runtime can tell whether the line is one
it can honour, so the guess would be made later, by whichever runtime got there
first:

```bash
cargo run -p pact-cli -- check tests/trees/a-plugin-with-no-registry
```

```
error: 'crm-tools' asks for the package 'acme-crm-tools', which names no registry —
       so no runtime can say whether it is one it can load.
  --> a-plugin-with-no-registry/plugins/crm-tools.yaml:2:1
  fix: Write one of the registries a runtime loads from — `npm` or `pypi` — in
       front of the name: `npm:acme-crm-tools` for an npm package,
       `pypi:acme-crm-tools` for a Python one.
  rule: loader/plugin-package-has-no-registry
```

The version range is not judged until the registry is known, because which
grammar it is read in is the registry's to say. Held by
`crates/pact-cli/tests/a_plugin_is_named_and_never_loaded.rs`.
