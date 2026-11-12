# The 68 kinds

Generated from `spec/schema.yaml`. Every kind, what it is for, and how
many fields it has. You do not need to learn these — `pact check` names the
right one when you need it.


**68 kinds.** A kind is a *shape a document can take*, not a file you must
write: most workspaces use a dozen.


## Agents and behaviour

| Kind | Fields | Core fields |
|---|---:|---|
| `action` | 21 | `description`, `topics`, `takes`, `reads-only`, `needs-a-person` |
| `agent` | 29 | `name`, `description`, `instructions`, `team`, `teamwork` |
| `loop` | 4 | `description`, `based-on` |
| `knowledge` | 15 | `description`, `topics`, `documents`, `passages-at-most`, `must-cite` |
| `skill` | 14 | `name`, `description`, `use-when`, `do-not-use-when`, `if-unsure` |
| `stage` | 32 | `does`, `says`, `asks`, `call`, `may-call` |
| `tool` | 17 | `description`, `connect`, `url`, `method`, `says` |
| `program` | 7 | `description` |
| `program-fuel` | 4 | — |
| `value` | 4 | `description`, `rows-are`, `value` |
| `variant` | 6 | — |
| `turn` | 6 | — |
| `voice` | 9 | — |
| `workspace` | 39 | `name`, `workspace-id`, `description`, `owner`, `profile` |

## Topics, events and reactions

| Kind | Fields | Core fields |
|---|---:|---|
| `topic` | 2 | `description`, `noticed-by` |
| `event` | 6 | `description`, `at`, `when-this`, `more-than`, `topic` |
| `reaction` | 10 | `description`, `event`, `at`, `when-this`, `more-than` |
| `reaction-step` | 4 | `remind`, `consult`, `tell`, `stop` |
| `subscription` | 3 | `topic`, `event`, `how` |

## Workflows

| Kind | Fields | Core fields |
|---|---:|---|
| `workflow` | 17 | `description`, `accepts`, `answers-with`, `starts-at`, `steps` |
| `if-it-fails` | 8 | `after-that`, `gives-up-after`, `backup`, `carry-on-with`, `asks` |
| `reminder` | 5 | `at`, `nudges`, `tells`, `hands-over-to`, `runs` |
| `moment` | 5 | `at`, `after`, `before`, `counted-in`, `in-time-zone` |
| `rung` | 5 | `rules`, `agent`, `if-unsure-below`, `if-it-disagrees`, `asks` |
| `route-rule` | 3 | `when`, `choose`, `because` |
| `ownership` | 3 | `owned-by`, `locked`, `locked-until` |
| `release` | 1 | `asks` |

## People and permission

| Kind | Fields | Core fields |
|---|---:|---|
| `credential-reference` | 1 | `by-reference` |
| `interceptor` | 6 | `description`, `when`, `applies-to`, `may`, `rules` |
| `policy` | 2 | `applies-to`, `ask-a-person` |
| `question` | 20 | `description`, `says`, `answer`, `shows`, `asked-of` |
| `question-rule` | 4 | `when`, `because`, `question`, `first-times` |
| `redaction` | 2 | `description`, `hide` |
| `detector` | 3 | `description` |

## Limits and models

| Kind | Fields | Core fields |
|---|---:|---|
| `call-order` | 2 | `call`, `first` |
| `benchmark` | 5 | — |
| `catalog` | 4 | — |
| `figure` | 2 | — |
| `limits` | 24 | `feel`, `finishes-within`, `starts-from`, `paused-during`, `milestones` |
| `model` | 11 | — |
| `model-can` | 12 | — |
| `model-cost` | 2 | — |
| `model-speed` | 1 | — |
| `needs` | 12 | `reasoning`, `tool-calling`, `images`, `audio`, `computer-use` |
| `provenance` | 6 | — |
| `served-by` | 3 | — |

## Memory and context

| Kind | Fields | Core fields |
|---|---:|---|
| `context-policy` | 7 | `description`, `when-full`, `always-keep`, `if-it-still-does-not-fit`, `asks` |
| `state` | 15 | `description`, `lasts`, `forget-after`, `kept-for`, `kept-per` |
| `tidy-step` | 3 | — |

## Working together

| Kind | Fields | Core fields |
|---|---:|---|
| `bundle` | 5 | `description`, `version`, `from`, `brings` |
| `port` | 22 | `description`, `kind`, `every`, `says`, `if-still-running` |
| `resource` | 14 | `resource-kind`, `endpoint`, `auth`, `asks-to-connect`, `description` |
| `published` | 5 | — |
| `published-tool` | 4 | — |
| `teamwork` | 9 | `may-start`, `waits-for`, `enough-is`, `gives-up-after`, `starts` |
| `when-this` | 12 | `tool`, `value`, `arg`, `more-than`, `less-than` |
| `comparand` | 3 | `value`, `now-plus`, `now-minus` |

## Measuring and learning

| Kind | Fields | Core fields |
|---|---:|---|
| `case` | 8 | `when`, `with`, `turns`, `expect`, `because` |
| `cycle-limits` | 3 | `per-cycle`, `per-month`, `evals` |
| `drift` | 1 | `at-most` |
| `eval-rule` | 8 | `must-say-one-of`, `must-contain`, `must-not-contain`, `must-call-before`, `judged` |
| `evals` | 12 | `description`, `population`, `from-the-last`, `sample`, `reviewed-by` |
| `learning` | 8 | `enabled`, `may-improve-on-its-own`, `needs-a-person-to-approve`, `keep-only-if`, `review` |
| `learning-model` | 2 | — |
| `metric` | 4 | — |
| `outcome` | 8 | `declined`, `nobody-answered`, `heard` |

## Observing

| Kind | Fields | Core fields |
|---|---:|---|
| `settings` | 12 | `max-tokens`, `thinking` |
| `watch` | 3 | `description`, `when`, `writes-to` |

---

## How to read a kind

Every kind follows the same shape, so 54 is not 54 things to learn:

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
