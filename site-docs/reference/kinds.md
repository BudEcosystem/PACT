# The 47 kinds

Generated from `spec/schema.yaml`. Every kind, what it is for, and how
many fields it has. You do not need to learn these — `pact check` names the
right one when you need it.


**47 kinds.** A kind is a *shape a document can take*, not a file you must
write: most workspaces use a dozen.


## Agents and behaviour

| Kind | Fields | Core fields |
|---|---:|---|
| `action` | 9 | `description`, `takes`, `reads-only`, `needs-a-person`, `spends-money` |
| `agent` | 23 | `name`, `description`, `instructions`, `team`, `teamwork` |
| `loop` | 4 | `description`, `based-on` |
| `knowledge` | 9 | `description`, `documents`, `passages-at-most`, `must-cite`, `use-when` |
| `skill` | 11 | `name`, `description`, `use-when`, `do-not-use-when`, `if-unsure` |
| `stage` | 6 | `says`, `asks` |
| `tool` | 7 | `description`, `connect`, `url`, `method`, `says` |
| `program` | 7 | `description`, `engine`, `determinism`, `takes`, `answers-with` |
| `program-fuel` | 4 | — |
| `value` | 3 | `description`, `value` |
| `variant` | 5 | — |
| `workspace` | 26 | `name`, `workspace-id`, `description`, `owner`, `profile` |

## People and permission

| Kind | Fields | Core fields |
|---|---:|---|
| `credential-reference` | 1 | `by-reference` |
| `interceptor` | 6 | `description`, `when`, `applies-to`, `may`, `rules` |
| `policy` | 2 | `applies-to`, `ask-a-person` |
| `question` | 8 | `description`, `says`, `answer`, `shows`, `asked-of` |
| `question-rule` | 3 | `when`, `because`, `question` |
| `redaction` | 2 | `description`, `hide` |

## Limits and models

| Kind | Fields | Core fields |
|---|---:|---|
| `call-order` | 2 | `call`, `first` |
| `catalog` | 3 | — |
| `figure` | 2 | — |
| `limits` | 13 | `feel`, `finishes-within`, `cost-per-request-under`, `steps-at-most`, `tool-calls-at-most` |
| `model` | 8 | — |
| `model-can` | 5 | — |
| `model-cost` | 2 | — |
| `needs` | 8 | `reasoning`, `tool-calling`, `images`, `audio`, `computer-use` |
| `provenance` | 6 | — |
| `served-by` | 2 | — |

## Memory and context

| Kind | Fields | Core fields |
|---|---:|---|
| `context-policy` | 7 | `description`, `when-full`, `always-keep`, `if-it-still-does-not-fit`, `asks` |
| `state` | 8 | `description`, `lasts`, `forget-after`, `never-from`, `survives-shortening` |
| `tidy-step` | 3 | — |

## Working together

| Kind | Fields | Core fields |
|---|---:|---|
| `bundle` | 5 | `description`, `version`, `from`, `brings` |
| `port` | 10 | `description`, `kind`, `every`, `says`, `if-still-running` |
| `resource` | 6 | `resource-kind`, `endpoint`, `auth`, `asks-to-connect`, `description` |
| `teamwork` | 8 | `waits-for`, `enough-is`, `gives-up-after`, `starts`, `divides-the-budget` |
| `when-this` | 3 | `tool`, `arg`, `more-than` |

## Measuring and learning

| Kind | Fields | Core fields |
|---|---:|---|
| `case` | 6 | `when`, `with`, `expect`, `because`, `must-also` |
| `cycle-limits` | 3 | `per-cycle`, `per-month`, `evals` |
| `drift` | 1 | `at-most` |
| `eval-rule` | 6 | `must-say-one-of`, `must-contain`, `must-not-contain`, `must-call-before`, `judged` |
| `evals` | 7 | `description`, `population`, `must-pass`, `rules`, `graded-by` |
| `learning` | 8 | `enabled`, `may-improve-on-its-own`, `needs-a-person-to-approve`, `keep-only-if`, `review` |
| `learning-model` | 2 | — |
| `metric` | 3 | — |
| `outcome` | 3 | — |

## Observing

| Kind | Fields | Core fields |
|---|---:|---|
| `settings` | 12 | `max-tokens`, `thinking` |
| `watch` | 3 | `description`, `when`, `writes-to` |

---

## How to read a kind

Every kind follows the same shape, so 47 is not 47 things to learn:

```yaml
description: what this is, in one line     # every kind has this
<the two or three fields that kind needs>
```

Each field carries three things the schema enforces:

| | |
|---|---|
| `help:` | one line explaining it to somebody who cannot write code |
| `surface:` | its governance class — see [Governance](../concepts/governance.md) |
| `tier:` | `core` (you will need it) or `expert` (you probably will not) |

**A field with no `help:` cannot exist.** `pact check` refuses to validate
against a specification that leaves one out, because nothing could then tell an
author what they were being asked for.

## You do not need to learn these

Most workspaces use about a dozen. When you need one you do not have,
`pact check` names it:

```
error: 'loop' names 'carefull', and there is no such entry in `loops:`.
  fix: Change it to one of: careful, pact:loop/answer-more-than-once, pact:loop/plan-then-do, pact:loop/react, pact:loop/reflexion, pact:loop/standard, pact:loop/tree-of-thought — or add a file `loops/nonsense.yaml`.
       — or add a file `loops/carefull.yaml`.
```

## Where each is defined

All of them live in `spec/schema.yaml`, which is **itself a PACT document**
loaded by the same loader. Adding a field to the specification is a YAML edit.

!!! note "One honest exception"
    A *package-shaped* kind — one whose folder form is `watch/slow-tools/watch.yaml`
    rather than a field inside another file — also needs one word in the loader's
    list of kind stems. The claim is "one word, the same one every kind costs",
    not "no code change ever".
