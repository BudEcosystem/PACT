# pact-lang

The PACT language: one `.pact` file that says what a folder of YAML and
Markdown says. This crate reads such a file into a document and prints a
document as such a file. It checks nothing and runs nothing.

```text
agent support
  description: Answers customers about their orders.
  uses orders, billing
  at most 10 steps

  when the work touches finance
    consult finance-desk
```

For how to *write* the language, read `site-docs/reference/language.md`. This
page is for somebody changing the crate.

## Where it sits

```text
   team.pact ──► pact-lang::read ──┐
                                   ├──► one document ──► pact-schema, pact-loader rules ──► adapters
   a folder  ──► pact-loader ──────┘
                                   │
   team.pact ◄── pact-lang::write ◄┘        (pact write, pact build)
```

`pact-loader` calls `read` when it meets a file ending in `.pact`
(`crates/pact-loader/src/lib.rs`). From there on nothing knows which form the
workspace was written in. That is the design: **the language has no checker
and no meaning of its own.** A rule written once holds for both forms, because
there is only one document to hold it for.

The document is `pact_doc::Node`: a value with the place it came from (file,
line, column). The reader gives every value its real place in the `.pact`
file, so an error found later by any rule points at the line the author wrote.

## The four files

| File | What is in it |
|---|---|
| `src/lib.rs` | The table of header words (`agent` → `agents:`), the five single documents, and `slug`, which makes a name from a sentence |
| `src/read.rs` | The reader: `read(text, file) -> Parsed { node, diagnostics }` |
| `src/read/flow.rs` | Statements: a workflow's steps written in the order they run, read into `steps:`, `starts-at:` and each step's `then:` |
| `src/write.rs` | The printer: `write(root)` for one `.pact` file, `tree(root)` for a folder, `one_file(root)` for a single `workspace.yaml` |
| `src/write/flow.rs` | Statements, printed: only for the wirings an order of lines can say, and settings for the rest |
| `src/emit.rs` | How one value becomes text: when a string needs quotes, when a list fits on one line, when text can be a block |

## How the reader works

1. **Lines.** The text is split into lines with their indentation. A tab in
   the margin is refused once, at the first one.
2. **Blocks.** A line at the margin is a header. Its word is looked up in the
   table in `lib.rs`; an unknown word gets the nearest one suggested.
3. **Body lines.** For each line in a block the reader tries, in order: a
   sentence this kind of block knows, then a setting, then a text block.
   Sentences come first so that `when it runs out: stop and say so` is not
   read as a setting named `when it runs out`.
4. **Settings go to the YAML reader.** A setting, with everything indented
   under it, is handed as text to `pact_doc::parse_yaml_at` with the offset it
   sits at. The language has no second YAML reader, so it cannot disagree with
   the folder form about what a value means.
5. **Sentences build the same fields.** Each sentence writes into the block's
   map exactly what the settings would have: `uses a, b` puts `[a, b]` under
   `uses`.
6. **Nothing is written twice.** `put` refuses a field set twice
   (`lang/said-twice`), with one exception: two maps under one key are merged,
   so `at most 8 steps` and `when it runs out: …` can both add to `limits`.
   `push` is for the lists sentences build one line at a time (`then`,
   `listens-for`, `reactions`, `ask-a-person`).

`Kind` says which sentences a block knows: `Agent`, `Tagged` (tool and
knowledge), `Policy`, `Reaction`, `Event`, `Flow` (workflow and loop),
`Program`, `Plain` (settings and text blocks only). Two more are used only
inside a workflow: `Stage`, for the inside of a loop, and `Decision`, for
what sits beneath a `decide`.

### Statements

A workflow in the document is a set of named stages, each saying where to go
next. `read/flow.rs` reads a list of statements into that:

1. Each statement becomes a `Step`: its name, its fields, and how it ends
   (`Goes` on to the next, `Answers`, or `Decides`).
2. `place` gives each `Goes` step a `then: { answered: <next> }`, unless a
   `then:` written beneath it already says `answered:`.
3. The statements beneath an `if` are placed beside the `decide`, and the last
   of each goes on to whatever follows the `decide`.
4. A path such as `plan.findings` becomes `steps.plan.findings` (`bound` in
   `lib.rs`); `unbound` is its inverse for the printer, and a unit test holds
   that the two undo each other.

`write/flow.rs` is the less certain half, because stages can be wired in ways
no order of lines can say. It writes statements for the wirings it knows and
returns `None` for the rest. It does not need to be right about which is
which: the block is read back and compared, as every block is, and a workflow
that does not come back the same is written as settings.

## How the printer works

The printer's job is harder than the reader's, because it must never print a
file that reads back as a different workspace.

It does not rely on knowing every field. For each block it:

1. writes the block, using sentences where it has one;
2. **reads its own text back** with `read`;
3. compares the result with the block it started from, as canonical JSON;
4. if they differ, writes the block again more plainly.

There are three levels, tried in order: *rich* (sentences), *plain* (settings
only), *safe* (settings, with every string in double quotes). A new field
added to `spec/schema.yaml` needs no change here: it is printed as a setting.

Things that are files by nature, such as a knowledge set's documents, are not
put in the file. `write` returns them in `left_as_files` and `pact write`
says so.

## Adding a sentence

1. **Reader.** In `read.rs`, add the opening to the list for its `Kind` (the
   list is what `lang/not-a-line` suggests from), and a branch in `sentence`
   that writes the fields.
2. **Printer.** In `write.rs`, write the sentence when the fields have the
   shape it can say, and fall through to a setting when they do not. You do
   not have to be exhaustive: step 2 of the printer catches a sentence that
   does not read back.
3. **Test.** Add a case to `tests/every_sentence_means_one_thing.rs` holding
   the sentence to the settings it stands for.
4. **Documentation.** Add the row to `site-docs/reference/language.md` and to
   §4.3 of `docs/99-THE-PACT-LANGUAGE.md`.

Adding a *kind of block* is one row in `COLLECTIONS` in `lib.rs`. A test in
`pact-cli` (`every_collection_has_a_header_word`) fails when the specification
gains a collection and this table does not.

## What holds it

| Test | Holds |
|---|---|
| `tests/a_workflow_is_written_in_the_order_it_runs.rs` | each statement against the stages it stands for; `let`; `based on … with …`; what is refused and on which line |
| `tests/every_sentence_means_one_thing.rs` | each sentence against the settings it stands for; each mistake against its rule and its line |
| `crates/pact-cli/tests/the_language_and_the_folder_are_one_workspace.rs` | every workspace under `examples/` printed and read back to the same document; `pact build`; several files in one folder; the header-word table |
| `crates/pact-cli/tests/discovery.rs` | a workspace written both ways has one digest |

```bash
cargo test -p pact-lang
cargo test -p pact-cli --test the_language_and_the_folder_are_one_workspace
```

## What it does not do

- It does not carry comments from one form to the other.
- It has sentences for agents, tools, sets of documents, policies, reactions,
  events, workflows, loops and programs. Everything else is settings.
- It has no expressions. A path in a statement is a path in the document.
- It does not know what any field means. If you find yourself wanting it to,
  the thing you want belongs in `pact-schema` or `pact-loader`.
