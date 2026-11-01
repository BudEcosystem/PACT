# One contract, several providers

## The problem

A templated agent that sends email cannot name Gmail: the next customer uses
Outlook. And an approval rule written against `gmail/send-message` would not hold
on Outlook at all.

## An interface, and its implementations

```yaml title="tools/email.yaml — the contract, written once"
description: The customer's own mailbox, whichever one they connected.
category: email
interface: yes
chosen-by: run-inputs.mailbox     # or the-host: whatever account the person connected
actions:
  send-message:
    description: Send one message from the shop.
    takes: {to: text, subject: text, body: text}
    needs-a-person: yes
    inspects: [to]
```

```yaml title="tools/gmail.yaml — one provider"
description: Gmail, through the platform team's MCP server.
implements: email
connect: gmail-server
actions:
  send-message:
    calls: send_email                         # the server's own name for it
    passes: {recipient: to, html_body: body}  # the server's names for the arguments
```

The agent writes `uses: [email]`. A policy, an eval and the model's view of the
tool are all written against `email`, so they mean the same thing whichever
provider runs. Pinning one is still `uses: [gmail]`.

## The rule that keeps it safe

An implementation may say only **how** it reaches its own server — `calls:`,
`passes:`, and `needs-a-person: yes`, which only ever asks more. Restating what an
action takes, or saying it needs no person where the interface says it does, is
refused. The loader then writes the interface's contract into each
implementation, so every check below reads Gmail as though it were written out in
full.

## Categories, skills and documents

`category: email` is a label for finding tools; it promises nothing about what two
tools in it take. The same `interface:` / `implements:` / `chosen-by:` lines work
on **skills** (each shop's own refund procedure) and on **knowledge** (each
customer's own documents).
