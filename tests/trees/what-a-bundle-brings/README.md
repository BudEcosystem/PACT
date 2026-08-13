# what-a-bundle-brings

A workspace that names two ready-made sets of capabilities. One of them is here;
the other is not, and PACT says so out loud.

```
workspace.yaml
agents/desk/agent.yaml
agents/desk/instructions.md
bundles/customer-lookup/customer-lookup.yaml
bundles/customer-lookup/contributes/tools/find-customer.yaml   <- its folder is here
bundles/refund-toolkit/refund-toolkit.yaml                     <- its folder is not
```

The two bundle folders differ in exactly one thing: whether a `contributes/`
folder sits beside the self file.

## What this tree is for

`bundles:` is how a workspace says *"these capabilities came from somewhere
else"*. Every rule PACT holds a bundle to — that it contributes only the kinds
its `brings:` line names, and that an author is told when nothing mounted it —
was tested only against documents the test built in memory. No shipped tree
declared a bundle at all:

```bash
find examples tests -type d -name bundles   # before this tree existed: nothing
```

(The register asked that with `grep -rn "bundles:" examples/ tests/`, which also
returned nothing — and would have kept returning nothing however many trees
declared a bundle, because a bundle is a **folder** and nobody types the word.
Run it now and you get two hits, both of them prose on this page.)

That matters more here than it usually would, because **`contributes:` is not
something an author types.** Its own line in `spec/schema.yaml` says so: *"You do
not type this — it is what is in the bundle's own folder."* So either the folder
form produces it or nothing does, and a document assembled by a test cannot tell
you which. This tree is the answer written down: a real folder, read by the real
loader.

## Try it

```bash
cargo run -p pact-cli -- check tests/trees/what-a-bundle-brings
```

```
warning: the bundle 'refund-toolkit' names `from: acme/refund-toolkit` and
         nothing here mounted it, so none of its definitions are in this workspace.
  --> tests/trees/what-a-bundle-brings/bundles/refund-toolkit:1:1
  fix: Nothing to type if the system running this resolves 'refund-toolkit'
       itself. Otherwise copy what it defines into this tree — a bundle is a
       folder of the same documents, so mounting one costs reading files and
       nothing else.
OK — tests/trees/what-a-bundle-brings loaded with 1 warning(s).
```

Nothing is said about `customer-lookup`, whose folder is here. That difference —
one warning, not two and not none — is what the check is for.

## Why it lives here and not in `examples/`

`scripts/test-all.sh` runs `pact check --deny-warnings` over every workspace
under `examples/`, because a warning in a shipped example is teaching somebody
the wrong thing. This tree **must** warn: the warning is the behaviour being
exercised. Under `examples/` it would either turn the gate red or force
`loader/bundle-not-mounted` to be quietened, and quietening a diagnostic to keep
a script green is how a checker stops checking.

`tests/trees/` is where a real, loadable, documented workspace goes when its
whole point is a diagnostic. `tests/trees/one-line-gate/` is the other one.

```bash
cargo run -p pact-cli -- check tests/trees/what-a-bundle-brings                  # exit 0
cargo run -p pact-cli -- check tests/trees/what-a-bundle-brings --deny-warnings  # exit 1
```

## What this tree also shows, which is that mounting is unbuilt

`agents/desk/` has no `uses:` line. Add one naming the tool the bundle
contributes and `pact check` refuses it:

```yaml
uses:
  - find-customer
```

```
error: 'uses' names 'find-customer', and there is no such entry in `tools:`,
       `skills:` or `knowledge:`.
  fix: Nothing is declared there yet. Add a file `tools/find-customer.yaml`, …
```

The tool is in the document. It is not in the workspace's `tools:`, because
nothing in this project projects a bundle's contributions into the collections an
agent can name — so the fix offered is to write a second copy of a file this tree
already holds. What that would take, and the four decisions nobody has made about
it, is written down in `docs/remediation/C7-bundle-mounting.md`.

Tests: `crates/pact-loader/tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs`.
