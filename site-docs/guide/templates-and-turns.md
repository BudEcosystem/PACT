# Templates and written conversations

## Words filled in when a run starts

`{{run-inputs.brand}}` in an agent's instructions is filled by the run, and a
hole naming nothing the agent declares is refused. For words that also **choose
and repeat**, a workspace writes `template-language: jinja`:

```yaml title="agents/desk/agent.yaml"
instructions: |
  You answer the phone for {{ run_inputs.shop_name }}.
  {% if run_inputs.tier == "gold" %}Offer the free returns label.{% endif %}
```

Names use `_` where PACT writes `-` (`run-inputs.brand` is subtraction in Jinja).
Only the filters both runtimes render identically are allowed; includes, macros
and function calls are refused; a picture or a recording cannot be printed. What
is filled in is data and is never rendered again — a customer who types
`{{ 7*7 }}` is quoted, not obeyed.

## Turns

A conversation can be written down — a worked example a small model needs, or the
history of a multi-turn eval case:

```yaml
turns:
  - from: developer
    says: Every caller has been told the call may be recorded.
  - from: user
    says: Did you get my email about the broken kettle?
  - from: agent
    calls: email/search-messages
    with: {query: broken kettle}
  - from: tool
    answer: One message, sent yesterday.
  - from: agent
    says: Yes — I have it here.
```

Five speakers: `system`, `developer`, `user`, `agent`, `tool`. Standing
instructions come first, because two of the three large providers cannot place
one mid-conversation; every call is answered by the next turn; a case's last turn
is the person's, because the agent's next reply is what is graded.
