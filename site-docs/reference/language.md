# The PACT language

The complete reference for a `.pact` file. For a first read, start with the
guide: [One file instead of a folder](../guide/the-pact-language.md), or the
tutorial: [Your first agent, in one file](../guide/first-agent-in-one-file.md).

A `.pact` file is a second way of writing a PACT workspace. It is read into
the same document as the folder of YAML and Markdown, by the same loader, so
every rule `pact check` has applies to it unchanged and every adapter runs
what comes out. The language adds no meaning of its own: anything it can say,
the folder can say, and the other way round.

## The shape of a file

```text
<block header>            ← starts at the left margin
  <body line>             ← indented under it
  <body line>
    <lines that belong to the body line above>

<block header>
  …
```

- **Blocks** start at the left margin. Everything indented beneath a header
  belongs to that block, up to the next line at the margin.
- **Indent with spaces**, two for each level. A tab in the margin is refused
  (`lang/a-tab-in-the-margin`), because how far a tab reaches depends on the
  editor showing it.
- **Lines of one body line up.** A line indented less than its neighbours and
  more than the header is refused (`lang/does-not-line-up`).
- **Blank lines mean nothing.** Use them to group lines.
- **Order means nothing.** Blocks can be written in any order, and so can the
  lines inside one, with one exception: the steps of a reaction are carried
  out in the order they are written.

## Block headers

| Header | Holds | Name |
|---|---|---|
| `workspace "<name>"` | the workspace's own settings: `description:`, `owner:` and the rest | the display name, in quotes |
| `<kind> <name>` | one entry of a collection | a short name: letters, digits and dashes |
| `agent <name> "<display name>"` | an agent | the short name, then optionally the name people read |
| `redaction`, `evals`, `learning`, `release`, `models` | the five things a workspace has only one of | none |
| `when <signal>` | a reaction that covers every agent | made from the sentence, or given by a `called` line |

The kind words, each with the collection it adds to:

| Word | Collection | | Word | Collection |
|---|---|---|---|---|
| `agent` | `agents:` | | `resource` | `resources:` |
| `tool` | `tools:` | | `program` | `programs:` |
| `workflow` | `workflows:` | | `value` | `values:` |
| `policy` | `policies:` | | `port` | `ports:` |
| `question` | `questions:` | | `shape` | `shapes:` |
| `loop` | `loops:` | | `remembers` | `remembers:` |
| `topic` | `topics:` | | `detector` | `detectors:` |
| `event` | `events:` | | `owner` | `owners:` |
| `reaction` | `reactions:` | | `context-policy` | `context-policies:` |
| `knowledge` | `knowledge:` | | `bundle` | `bundles:` |
| `skill` | `skills:` | | `interceptor` | `interceptors:` |
| | | | `watch` | `watch:` |

A test holds this table to the specification
(`every_collection_has_a_header_word`): a collection added to
`spec/schema.yaml` with no header word fails the build.

A name with a space or a `#` in it is written in double quotes:
`tool "returns desk"`. Only an agent takes a second, quoted name
(`lang/a-second-name` otherwise).

## Body lines

An indented line is one of three things. The reader decides which in this
order.

### 1. A sentence

A line that starts with one of the openings the block's kind knows. The
sentences are listed [below](#sentences). They are checked first so that
`when it runs out: stop and say so` is read as the sentence it is and not as a
setting called `when it runs out`.

### 2. A setting

`key: value`, exactly as in a YAML file, with anything YAML allows beneath it:

```text
tool orders
  description: Looks up an order.
  actions:
    find:
      description: Finds one order by its number.
      takes:
        order-number: text
      reads-only: yes
```

The text from the key to the end of its indented lines is handed to the same
YAML reader the folder form uses, at its real line and column, so a mistake
inside a setting is reported exactly where it is. **Every field in the
specification can be written as a setting.** That is what makes the language
complete: a field with no sentence is still one line away.

### 3. A text block

A field's name alone on a line, with the text indented beneath it:

```text
agent helper
  instructions
    Answer the customer's question about returns. Be brief.

    Say when you are not sure rather than guessing.
```

The text is kept as written: line breaks, blank lines and deeper indentation
all stay, and a `#` in it is part of the text. This is the one place a long
piece of writing reads the way it would in a Markdown file. Any field that
holds text can be written this way; `instructions` is the common one.

A line that is none of the three is refused with `lang/not-a-line`, and the
fix names the nearest sentence.

## Sentences

A sentence is a shorter way of writing one or more settings. Nothing can be
said with a sentence that cannot be said with settings.

### In an agent

| Sentence | The same as |
|---|---|
| `takes <field>: <shape>, <field>: <shape>` | `accepts:` with one line for each field |
| `gives <field>: <shape>, …` | `answers-with:` |
| `uses <name>, <name>` | `uses:` |
| `asks <agent>: <what for>` | one line of `team:` |
| `at most <n> steps` | `limits.steps-at-most:` |
| `at most <n> tool calls` | `limits.tool-calls-at-most:` |
| `at most <n> tokens` | `limits.tokens-at-most:` |
| `spends under <money> a request` | `limits.cost-per-request-under:` |
| `when it runs out: <what>` | `limits.when-it-runs-out:`, with the spaces of `<what>` read as dashes |
| `remembers <name>`, with settings beneath | one entry of `remembers:` |
| `listens for topic <topic>: asked first` | `listens-for: [{topic: …, how: asked-first}]` |
| `listens for event <event>: told after` | `listens-for: [{event: …, how: told-after}]` |
| `when <signal>`, with steps beneath | a reaction, added to the workspace's `reactions:` and to this agent's own `reactions:` list |

A shape is written as in the folder form: `text`, `money`, `list of images`,
`one of approved, declined`. Because `one of a, b` has a comma in it, the
reader splits a `takes` or `gives` line only where a new `<field>:` begins.

### In a tool or a set of documents

| Sentence | The same as |
|---|---|
| `about <topic>, <topic>` | `topics:` |

### In a policy

| Sentence | The same as |
|---|---|
| `before <tool>/<action>: ask <question>, because <why>` | one rule of `ask-a-person:` |
| `before <tool>/<action>, when <arg> is more than <amount>: ask <question>, because <why>` | the same rule, narrowed by an argument |

### In a reaction

These are written under `when <signal>`, or under a `reaction <name>` block.

| Sentence | The same as |
|---|---|
| `remind it: <text>` | a step `{remind: <text>}` |
| `consult <agent>` | a step `{consult: <agent>}` |
| `tell <agent>` | a step `{tell: <agent>}` |
| `stop and say: <text>` | a step `{stop: <text>}` |
| `called <name>` | the reaction's name, when the one made from its sentence will not do |
| `every time` | `fires: every-time` |

Everything else a reaction has (`description:`, `applies-to:`, `at:` beside a
judgement) is written as a setting beside the steps.

### Signals: what follows `when`

| After `when` | The same as |
|---|---|
| `the agent is about to call <tool>` or `<tool>/<action>` | `at: step.tool.before`, `when-this: [{tool: …}]` |
| `the agent has called <tool> more than <n> times` | the same, with `more-than: <n>` |
| `<tool>/<action> has answered` | `at: step.tool.completed`, `when-this: [{tool: …}]` |
| `the agent has taken more than <n> steps` | `at: step.run.started`, `more-than: <n>` |
| `a turn starts` | `at: turn.run.started` |
| `the agent is about to ask a teammate` | `at: step.delegate.before` |
| `the agent has written a step` | `at: step.message.after` |
| `the work touches <topic>` | `topic: <topic>` |
| `it looks like <description>` | `judged: yes`, with the sentence as the question the judge answers |
| `<event> happens` | `event: <event>` |

A `when` line that matches none of these is refused with `lang/not-a-signal`.
What each signal means at run time is in the
[reactions reference](reactions.md).

### The name a `when` block gets

A reaction needs a name, because agents list the reactions that cover them. A
`when` block's name is made from its sentence: `when the agent has taken more
than 6 steps` is named `the-agent-has-taken-more-than-6-steps`. A `called
<name>` line inside the block replaces that. Its `description:` is likewise
the sentence, capitalised, unless one is written.

## Comments and quotes

- A `#` with a space before it ends a header or a sentence: everything after
  it is a comment. A line that is only a comment is ignored.
- Inside a setting, comments follow YAML's own rule, which is the same one.
- Inside a text block, `#` is text. Instructions written in Markdown keep
  their headings.
- Inside double quotes, `#` is text.
- **Comments are not part of the workspace.** `pact write` and `pact build`
  do not carry them across.

## Where a file may sit

**On its own.** The file is the workspace:

```console
$ pact check team.pact
```

**At the top of a folder**, beside the things that are files by nature:

```text
staff-desk/
├── staff-desk.pact
└── knowledge/staff-handbook/documents/
    ├── expenses.md
    └── leave.md
```

`pact check staff-desk` reads the file and the folder as one workspace.

**Several files in one folder** are read as one workspace, so a large one can
be split by subject: `agents.pact`, `tools.pact`. Two files may each add
entries to the same collection. The same setting written in two files is
refused, with both places named (`loader/ambiguous-field`); neither is quietly
chosen.

A `.pact` file anywhere below the top of a folder is refused
(`loader/a-pact-file-below-the-top`): it would be unclear which workspace it
describes.

## Commands

| Command | Does |
|---|---|
| `pact check <file.pact>` | checks it, like any workspace |
| `pact show <file.pact>` | prints the loaded document as JSON |
| `pact write [PATH]` | prints the workspace at PATH, folder or file, as one `.pact` file |
| `pact build <file.pact> --to <folder>` | writes the folder of YAML and Markdown the file stands for |

`pact waits`, `pact discover` and `pact card` take a `.pact` file, or a
folder holding one, wherever they take a folder.

`pact build` refuses three things, each with its own rule: a path that is not
a `.pact` file (`cli/build-needs-a-pact-file`), no `--to` folder
(`cli/build-needs-a-folder`), and a `--to` folder that already has something
in it (`cli/build-into-something-there`). After writing, it reads the folder
back and compares it with the file; if a nested layout would not read back
the same, it writes one `workspace.yaml` instead, so what it leaves behind is
always the same workspace.

## What is guaranteed

**The round trip.** For every workspace, reading what `pact write` printed
gives back the same document as reading the workspace. A test does this for
every workspace under `examples/`.

It holds by construction. The printer writes each block, reads its own text
back with the reader, and compares the result with the block it started from.
If they differ it tries again in a plainer way, in three stages:

1. sentences where a sentence exists;
2. settings only;
3. settings with every piece of text in double quotes.

So a field added to the specification tomorrow, which this page has never
heard of, is still printed correctly: it is written as a setting.

**One set of rules.** There is no checker for the language. A `.pact` file is
turned into the document first, and the checker reads the document. A rule
cannot hold for one form and be missed by the other.

**Errors point at the file you wrote.** Every value remembers the file, line
and column it came from, in either form.

## What the reader refuses

All of these stop the check, name the line, and say what to write instead.

| Rule | Fires when |
|---|---|
| `lang/no-such-block` | a line at the margin starts with a word that is not a kind of block; the nearest one is suggested |
| `lang/a-setting-in-no-block` | a `key: value` line is at the left margin |
| `lang/a-line-in-no-block` | an indented line comes before any block |
| `lang/a-block-with-no-name` | `agent` or `tool` with nothing after it |
| `lang/a-second-name` | a second, quoted name on anything but an agent |
| `lang/not-a-line` | a body line is not a setting, a sentence this block knows, or a text block |
| `lang/not-a-signal` | `when` is followed by something that is not one of the signals |
| `lang/said-twice` | a setting, a block or a name is written twice |
| `lang/does-not-line-up` | a line's indentation matches nothing above it |
| `lang/a-tab-in-the-margin` | a line is indented with a tab |
| `lang/a-quote-left-open` | a double quote that is never closed |
| `lang/nothing-goes-under-this` | lines are indented under a one-line sentence, such as a limit |

An example of each kind of answer:

```text
error: This line is not a setting, and not a sentence this kind of block knows.
  --> bad1.pact:5:3
  |
5 |   use orders
  |   ^^^^^^^^^^
  fix: Did you mean a line starting `uses`?
  rule: lang/not-a-line
```

```text
error: 'agnt' does not start any kind of block.
  --> bad3.pact:3:1
  |
3 | agnt helper
  | ^^^^
  fix: Did you mean `agent`?
  rule: lang/no-such-block
```

## What is not there

- **Sentences for everything.** Workflows, loops, questions, evals and ports
  are written as settings.
- **Fixes that speak the language.** A fix that tells you to add a file, such
  as *"Add a file `tools/zendesk.yaml`"*, names the folder form even when the
  mistake is in a `.pact` file. The block to write is `tool zendesk`.
- **Comments across the two forms.** See above.
- **`pact build` from a folder.** It takes a `.pact` file. A folder that
  already holds documents or scripts is not rebuilt for you.

## Where it lives in the code

| Part | File |
|---|---|
| Header words and the collections they add to | `crates/pact-lang/src/lib.rs` |
| The reader | `crates/pact-lang/src/read.rs` |
| The printer, and the folder writer | `crates/pact-lang/src/write.rs` |
| How one value is written as text | `crates/pact-lang/src/emit.rs` |
| Where the loader reads a `.pact` file | `crates/pact-loader/src/lib.rs` |
| `pact write` and `pact build` | `crates/pact-cli/src/main.rs` |
| Design, and where the build differs from it | `docs/99-THE-PACT-LANGUAGE.md` |
