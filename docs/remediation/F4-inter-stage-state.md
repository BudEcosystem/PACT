# F4 — Somewhere to put a value between stages. **Refused.**

**The decision: there are no variables. Everything a stage learns reaches the
next stage as words in the conversation, and that stays true.**

---

## What cannot be written

*"Save the risk score the checker returned. In the last stage, put it in the
summary."*

**There is no slot.** A stage's whole inheritance is the message history, so
whatever a stage needs from an earlier one has to be *said*, and whatever was
said can be re-read, re-interpreted, or summarised away.

`remembers:` is the one construct that looks like the missing thing, and it is
not it. `adapters/python/src/pact_adapters/facts.py`:

```python
def from_document(doc: Mapping[str, Any], agent_key: str) -> "Facts":
```

Per agent. `held` is per run. And **only one thing in the entire system ever
writes one** — measured:

```bash
$ grep -rn "facts.record(" adapters/python/src/pact_adapters/
adapters/python/src/pact_adapters/harness.py:1667
```

which is:

```python
spec.facts.record(
    f"{w.asked_as or slot}-was-approved",
    f"cleared for {call.name} at step {i}",
)
```

One name shape, one writer, one meaning: *a person cleared this gate*. `Facts`
is the mechanism that keeps a shortening from destroying the evidence a
`policy:` depends on — an excellent mechanism, and a **survival** mechanism, not
a store. An author cannot put a number in it and nothing can read one out.

The same is true one level up. A teammate's answer reaches the parent as prose —
`harness.py:2900`:

```python
prior = "\n".join(f"{a.member} said: {a.text}" for a in grant.so_far if a.ok)
```

## What it would take

A named, typed, run-scoped slot: somewhere to write, somewhere to read, and a
shape so that reading it means something. That is three new nouns, and the third
one is the expensive one — the moment a slot has a type, the things that read it
want to compare it, and comparing it is **F1**.

It also needs an answer to *what a park does with it*. `Suspension` declares
nineteen fields and none of them is this:

```bash
$ grep -cwi "fact\|facts" adapters/python/src/pact_adapters/suspension.py
0
```

(`-w` matters: a plain `grep -ci fact` there returns 7, every one of them
`default_factory`.)

So a design here inherits the whole of the durability question along with the
slot.

## What it collides with

**D14, and the Expansion Rule's premise that a document is readable.** A
workspace with variables is a program, and the argument the format has already
made twice — once about predicates (AC-3.2's *"no `&&`"*), once about loop
conditions (`loops.py`'s *"the fourth place an author can write a condition"*) —
lands here in its strongest form, because a variable is not a fourth place to
write a condition, it is the thing conditions are written *about*.

**And T7, through the shortening.** A slot that survives a context policy is a
second `Facts` with different rules; a slot that does not survive one is a value
that silently becomes empty in the middle of a run. `facts.py` opens with
exactly that finding — *"a check that passes because its evidence is gone is
worse than a check that fails"* — and it took a whole mechanism to answer it for
one name shape.

## The price

**Anything a run needs to carry has to be said out loud, and said again.** In
practice:

1. **The author writes it into the instructions.** *"Repeat the reference number
   in your final answer."* It usually works. Nothing checks that it did, and on
   a smaller model it is the first thing to go — `docs/00-THESIS.md` §7.3's whole
   argument is that a weak executor fails at composition, and carrying a value
   across four stages is composition.
2. **Long conversations get expensive, and then get shortened, and then the
   value is gone.** The only thing that survives a shortening by declaration is
   an approval. A reference number, a risk score, a customer tier: each of them
   is ordinary prose to the tidier.
3. **`answers-with:` is the closest thing to a guarantee and it is a prompt.**
   The register's AC-5 row says so plainly: `answers-with-mode:` picks
   `prompted`, and the two modes that would constrain the answer at the provider
   are `MODES_NOTHING_HERE_DELIVERS`. So the declared shape of an answer is an
   instruction appended to the system text, honoured by the model's goodwill.

**The residue: `remembers:` reads like the thing it is not.** Its help talks
about what a run came to know, and an author who wants a scratchpad will find it
and write one. Today they get silence — `record` is deliberately silent for
anything undeclared, so a declared-but-never-recorded fact is indistinguishable
from a working one. The field's help should say that a run establishes exactly
one kind of fact and that the author cannot add a second, which is a
documentation change this decision now owes.
