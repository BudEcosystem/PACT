# F1 — Routing on what a tool said. **Refused.**

**The decision: no predicate over content, anywhere in the format.** The one
condition that can move a run to a different stage stays *"a tool called more
than N times"*.

---

## What cannot be written

*"If the fraud checker comes back high risk, go to the escalate stage."*

Three places in PACT take a condition, and none of them will carry that sentence.

**A loop stage** routes on how the stage ended, and the endings are closed —
`adapters/python/src/pact_adapters/loops.py`:

```python
OUTCOMES = ("used-a-tool", "answered", "too-many-times")
```

None of the three is about *what came back*.

**An interceptor** has six sentences, and they are the only six. Measured:

```bash
$ grep -cE "^\s+- say: " spec/schema.yaml
6
```

Three hide values. Two count calls to a named tool. One reads the answer for
words. Of those six, exactly **one** can send a run somewhere else:

> `if <a tool> is called more than <n> times in one run, go to the <stage> stage
> instead`

and its condition is a counter, not a value. The one sentence whose condition
does read content — `if the answer mentions "<word>", stop and say "<why>"` —
needs `stop-the-run`, is a plain lower-cased word test, and reads **what the
agent said**, not what a tool returned. It ends the run. It cannot route.

**An approval gate** compares a value and is the closest thing here to the
sentence above: `tool: fraud/check`, `arg: risk`, `is: high`. But it reads the
**arguments of a call about to be made**, so it can see the risk score somebody
passes *in* and never the one a checker hands *back*; and its only outcome is
*ask a person*. A gate is a pause, not a branch.

## What it would take

A predicate language: a way to name a value produced during the run, a set of
comparisons over it, and a destination. Minimally `when: <something> <op>
<value> → <stage>`, plus somewhere for `<something>` to come from — because
today nothing carries a tool's return value anywhere a rule can reach it. The
payload at `step.tool.completed` is text, and `interceptors.Carries` has three
flags and no column for structure.

## What it collides with

**`loops.py` argues against it in its own module note**, and the argument is not
about difficulty:

> A predicate language here would be the fourth place in this project where an
> author can write a condition, and D14's bar is a support lead editing YAML —
> not a fourth dialect for them to learn.

**D14** is the no-code ceiling: *"every feature must have a no-code
expression"*, maximum not minimum. A dialect with operators, values and
destinations is the thing that bar exists to keep out. **AC-3.2's** resolution
is the precedent and it went the other way for the same reason — the register's
own row: *"There is deliberately no `&&`: the conjunction is the map … an
expression language is a language, with precedence and parentheses, which is the
one thing a non-coder must never have to learn."*

And a fourth dialect is R57's shape: two ways to say one thing. A condition
written on a stage and the same condition written on an interceptor would both
load, and only one of them would be reviewed as behaviour.

## The price

**An author cannot express a decision that depends on a result.** That is the
whole of it, and it is not small — it is the ordinary shape of the work these
agents are bought for: high risk goes to a human, low risk clears; a customer on
the enterprise tier gets the other script; a document the retriever could not
find sends the run to *say so* rather than to *answer*.

What they must do instead, in order of how much it costs them:

1. **Put the decision in the instructions and hope.** *"If the fraud checker
   says high risk, stop and hand this to a person."* This is what every shipped
   example does, it works most of the time, and it is exactly the arrangement
   `docs/00-THESIS.md` §7.3 says degrades fastest on a smaller model — the whole
   reason this project exists. Nothing in `pact check` can tell you it did not
   happen, and nothing in the trace distinguishes a run that made the right call
   from one that never faced it.
2. **Turn the branch into a team.** Give `escalate` its own agent and let the
   parent choose. That works, and it costs a whole extra run: its own history,
   its own budget slice, its own latency.
3. **Turn the branch into a gate.** If — and only if — the value is an
   *argument* of the next call, `ask-a-person` will hold it. That buys a human
   in the loop, not a branch.

**And the honest residue: a support lead who reads `interceptor.rules` will
believe the format branches.** One of its six sentences says `go to the <stage>
stage instead` in plain English, and they will reach for it with the wrong
condition. The refusal costs the field its apparent generality, and the help
text is what has to carry the limit.
