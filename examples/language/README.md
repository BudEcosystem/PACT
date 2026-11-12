# Workspaces written in the PACT language

Three workspaces, each written as one `.pact` file instead of a folder of YAML
and Markdown. `pact check` reads them the same way it reads a folder.

| Folder | What it shows |
|---|---|
| [`hello`](hello) | The smallest workspace there is: one agent, five lines |
| [`finance-first`](finance-first) | Topics, events, reactions and two agents that listen. The same workspace as the folder [`examples/kernel/finance-first`](../kernel/finance-first), written the other way |
| [`staff-desk`](staff-desk) | A `.pact` file at the top of a folder, beside documents that stay files. The same workspace as [`examples/answers-from-documents`](../answers-from-documents) |

## Try it

From the top of the repository, with `pact` built (`cargo build -p pact-cli`
puts it at `target/debug/pact`):

```bash
pact check examples/language/hello/hello.pact
pact check examples/language/finance-first/finance-first.pact
pact check examples/language/staff-desk            # the folder: file and documents together
```

Print a folder as one file, and write a file out as a folder:

```bash
pact write examples/kernel/finance-first
pact build examples/language/hello/hello.pact --to /tmp/hello
```

## Reading `finance-first.pact`

Three things are worth finding in it.

- **`about finance`** under `tool billing`. That tags the tool with a topic,
  so the moment the tool is about to be used, the work is known to be about
  finance. Nothing is guessed.
- **`listens for topic finance: asked first`** under `agent finance-desk`.
  The finance desk asks to be consulted. Nothing in `agent support` names it.
- **The two `when` blocks inside `agent support`.** One counts steps, which is
  exact. The other, `when it looks like the customer is angry or upset`, is
  decided by a second model, which is a guess, so it may remind and may not
  stop the run.

## What holds these to the folder form

`crates/pact-cli/tests/discovery.rs` checks that each of the two twins has
the same digest as its folder. If you edit one side, edit the other.

The language itself: [`site-docs/reference/language.md`](../../site-docs/reference/language.md).
