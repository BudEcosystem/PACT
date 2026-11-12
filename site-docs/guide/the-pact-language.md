# One file instead of a folder

A PACT workspace is a folder of YAML and Markdown. It can also be **one file**,
written in the PACT language, and the two are the same workspace: `pact check`
reads either, every rule is the same rule, and every adapter runs what comes
out.

```text title="hello.pact"
workspace "Hello"

agent greeter
  description: Says hello.
  instructions: Greet whoever writes to you, in one friendly sentence.
```

```console
$ pact check examples/language/hello/hello.pact
OK — examples/language/hello/hello.pact loaded cleanly (6 settings).
```

## The three kinds of line

A file is a list of **blocks**. A block starts at the left margin — `workspace
"Its name"`, `agent refund-desk`, `tool payments` — and everything indented
under it belongs to it. An indented line is one of three things.

| Line | Looks like | Means |
|---|---|---|
| a **setting** | `description: Says hello.` | exactly that field. Anything you can write in a YAML file, you can write here, nested the same way |
| a **sentence** | `uses zendesk, payments` | the field or fields in the table below |
| a **text block** | `instructions` alone, with text indented under it | that field, holding the text as written |

Every field PACT has can be written as a setting, so nothing is out of reach.
The sentences are for the lines people write most.

## The sentences

| In | Sentence | The same as |
|---|---|---|
| agent | `takes message: text, photos: list of images` | `accepts:` |
| agent | `gives decision: one of approved, declined, reason: text` | `answers-with:` |
| agent | `uses zendesk, payments` | `uses:` |
| agent | `asks policy-checker: Checks the request against our policy.` | one line of `team:` |
| agent | `at most 8 steps` · `at most 20 tool calls` · `at most 50000 tokens` | lines of `limits:` |
| agent | `spends under 0.50 USD a request` | `limits.cost-per-request-under:` |
| agent | `when it runs out: stop and say so` | `limits.when-it-runs-out:` |
| agent | `remembers what-was-said`, with its settings indented under it | one entry of `remembers:` |
| agent | `listens for topic finance: asked first` | one line of `listens-for:` |
| tool, knowledge | `about finance, tax` | `topics:` |
| policy | `before payments/issue-refund, when amount is more than 200 USD: ask is-this-ok, because a large refund is a management decision` | one `ask-a-person:` rule |
| anywhere | `when the work touches finance`, with what to do indented under it | a [reaction](events-and-reactions.md) |

A line that is none of the three is refused, on that line, with the nearest
sentence:

```
error: This line is not a setting, and not a sentence this kind of block knows.
  --> team.pact:9:3
  |
9 |   use zendesk
  |   ^^^^^^^^^^^
  fix: Did you mean a line starting `uses`?
  rule: lang/not-a-line
```

## A larger example

```text title="examples/language/finance-first/finance-first.pact (part)"
agent support
  description: Answers customers about their orders.
  uses orders, billing
  at most 10 steps
  when it runs out: stop and say so

  when the agent has taken more than 6 steps
    called wrap-up
    description: A run that is taking long is told to finish with what it has.
    remind it: You have taken more than six steps on this request. Answer with what you have, and say plainly what you could not find out.

  instructions
    Help the customer with their order. Look the order up before you answer.

agent finance-desk
  description: Knows the rules for refunds, invoices and tax.
  listens for topic finance: asked first
  instructions
    You are asked before money moves. Say what the rule is, and what is missing.
```

`examples/kernel/finance-first` is the same workspace as a folder. `pact show`
prints the same document for both, and a test holds that.

## Files that stay files

Some things are files by nature: a knowledge set's documents, a skill's
scripts. Leave them where they would be in any workspace and put the `.pact`
file at the top of the folder:

```
staff-desk/
├── staff-desk.pact
└── knowledge/staff-handbook/documents/
    ├── expenses.md
    └── leave.md
```

`pact check staff-desk` reads both as one workspace. Several `.pact` files in
one folder are read as one, and anything written in two places is refused
rather than one being chosen.

## Going between the two

`pact write` prints any workspace as a PACT-language file:

```console
$ pact write examples/kernel/finance-first > finance-first.pact
```

`pact build` writes the folder a file stands for:

```console
$ pact build finance-first.pact --to finance-first
```

**What is guaranteed.** Reading what `pact write` printed gives back the same
document as reading the folder — for every workspace this repository ships, by
a test that does it for each one. It holds for fields the language has no
sentence for, and for fields added after this page was written, because the
printer reads its own text back and writes a setting wherever a sentence would
not come back the same.

**What is not carried across.** Comments. A comment is not part of the
document either form is read into, so `pact write` and `pact build` both drop
them; move the ones worth keeping by hand.

!!! note "What is not there yet"
    A fix that tells you to add a file — *"Add a file `tools/zendesk.yaml`"* —
    still names the folder form when the mistake is in a `.pact` file. The
    block to write is `tool zendesk`.
