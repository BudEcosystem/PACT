# Tool schemas from the server

## Which half moves

A tool that reaches an MCP server lists **which actions the agent may call** —
a decision, and the reviewer's — and used to copy **what each one takes** by hand,
a fact the server already publishes. The second half now comes from the server;
the first stays written here, because a server that adds a money-moving tool
between two runs is exactly what the list exists to stop.

```yaml title="tools/gmail.yaml"
connect: gmail-server
schemas-from: the-snapshot        # or the-server, or this-file (the default)
actions:
  send-message: {calls: send_email}
```

## The snapshot is in the tree

`pact-sync gmail-server --from-file tools.json` (or `--url`, against a live
server) records what the server offers into `resources/gmail-server.yaml` as
`published:` — every tool, its arguments and its wording, with one fingerprint
over all of it. A server that changes shows up as a diff in review, and
`pact check` holds every argument an approval rests on to what the server really
takes, without connecting.

## When the server changes anyway

```yaml title="resources/gmail-server.yaml"
if-it-changes: use-what-was-reviewed   # or stop-and-say-so, ask-a-person, use-the-new-one
```

A change to an action that spends money or needs a person, or to an argument an
approval rests on, always stops the run (or asks), whatever this line says. A tool
the server adds is never offered because it appeared; `unlisted-actions:
each-call-asks-a-person` offers it with a person's yes on every call.
