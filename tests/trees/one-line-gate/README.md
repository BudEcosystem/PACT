# one-line-gate

The smallest workspace that stops and asks a person before money moves.

Four files. The whole approval surface is **one line**, in `tools/payments.yaml`:

```yaml
    needs-a-person: yes
```

There is no `questions/` folder here and no `policies/` folder either, and a
refund still parks: whoever is running the agent is asked, they have thirty
minutes, and if nobody answers the run stops and says so. `pact waits` lists it
beside a gate written the long way, with the same deadline, the same audience and
the same timeout action, pointing at the line above.

## Why this tree exists

Gating one action used to cost three files and thirteen lines — a question, a
policy file, and a rule inside it naming `<tool>/<action>`. Eve charges one file
and two lines for the same gate. A measured first-time author needed four rounds
of diagnostics, and four concepts they had not met, before their first gate held.
That was the one surface where this format was harder to author in than the
system it has to beat.

`examples/refund-desk` deliberately does **not** use the short form. Its gates
are written out, because they need what the short form cannot say: a named team
(`support-leads`), a threshold (`more-than: 200 USD`), an escalation, and one
question that asks for an amount rather than a yes. That is the division of
labour — the long form is not legacy, it is what you write when the decision is
more than a yes — and where both are written about one action, the long form
wins and `pact check` says so.

## Try it

```bash
cargo run -p pact-cli -- check tests/trees/one-line-gate
cargo run -p pact-cli -- waits tests/trees/one-line-gate
```

Then delete the `needs-a-person: yes` line and run both again: the wait
disappears from the list, and `pact check` starts warning that money moves with
nobody asked.
