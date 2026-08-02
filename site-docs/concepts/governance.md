# Governance and refusal

## Why a format needs an opinion about this

An agent that can spend money, email customers or change records is a governance
object. The questions an organisation actually asks are:

- who approved this change?
- what can it do without asking?
- if it changes itself, what stops it?

A format that leaves these to the runtime has moved the hard part somewhere it
cannot be reviewed.

## How: every field declares its class

Each field in the schema carries a `surface:`, and the surface decides whether a
change can be applied automatically or needs a person.

| Class | Contains | Auto-apply? |
|---|---|---|
| CLASS-1 | general text — wording, descriptions | yes |
| CLASS-4 | `S-CAP`, `S-EXEC`, `S-GOV`, `S-META` — capability, execution, governance | **no** |

So *"reword the instruction"* and *"widen who this approval covers"* are
mechanically different, rather than a matter of whose judgement you trust.

!!! note "The specification refuses to be ungoverned"
    `pact check` will not validate against a specification that leaves a field
    with no `surface:` or `tier:` — it bails rather than proceeding. A field
    nobody classified is a field nobody can say who may change.

## Refusal, not degradation

The pattern throughout: **when something cannot be honoured, say so.**

```
error: `summarised-by: claude-opus-5` is only served off this machine, and this
       workspace says `allow-egress: []`.
  fix: write `summarised-by: qwen2.5-7b-instruct`, which runs here; or add `llm`
       to `allow-egress:` — which is a change a person has to approve.
```

Notice the shape: it offers the compliant path *first*, and names the override as
a governance act rather than an equivalent option.

Where a run cannot enforce something, it reports rather than pretends:

| Field | Means |
|---|---|
| `unmetered` | nobody could measure it |
| `unenforced` | this runtime does not do that |
| `never_reached` | it could never fire |

Three different failures, kept distinguishable — merging them would send a reader
hunting for a problem that does not exist.

## Secrets

A credential reference has exactly one field, so there is nowhere to put a
secret:

```yaml title="resources/zendesk-server.yaml"
auth: { by-reference: host/zendesk-credential }
```

```console
$ # with a literal token instead:
error: 'bearer-token' is not something a credential reference can have.
  fix: Remove it, or use one of: by-reference.
```

The help text tells you who to ask: *"the name your platform team publishes for
where this credential is kept — ask them; it is their list, not a file in here."*

## Self-improvement is gated

`learning.yaml` in the worked example says `enabled: propose-only`,
`auto-apply: no`, `keep-only-if: a-person-approves-it`, and comments *"Nothing
changes by itself."*

Two checks enforce that. Both were found to be **deletable with the whole suite
still green** — so tests now hold each one, written after mutation testing
proved the gap.

## What PACT refuses to do at all

- **Execute author code** at load or build time. A spec naming code to run makes
  `pact check` decide whether that code is safe, which is a supply-chain problem
  the format should not have.
- **Ship privileged built-ins.** A portable format that ships a shell is not a
  format, it is a runtime.
- **Silently pick a model that fails your evals.** It refuses, then recommends.
