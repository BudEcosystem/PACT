# METERED DESK — a workspace for tests/conformance/limits.json.
#
# What a run does when a ceiling is reached, each of the three ways an author
# can say: answer with what it has, stop and say so, or ask a person. Three
# clerks who differ in that line and in nothing else, one whose ceiling is on
# steps, and one with a ceiling on both, who can reach the two together.
workspace "Metered desk"
  description: Clerks who look things up, each with a ceiling on how much.

resource office
  resource-kind: mcp-server
  endpoint: host/office
  description: Where the ledger is reached.

tool ledger
  description: The office ledger.
  connect: office
  actions:
    look:
      description: Read one entry.
      reads-only: yes
      takes:
        entry: text

question keep-looking
  description: Asked when a clerk has used up its lookups.
  says: This clerk has used all its lookups. May it go on?
  answer:
    go-on: yes or no
  asked-of: [office-leads]
  answer-within: 1h
  if-nobody-answers: decline

agent answers
  description: Looks entries up, and answers with what it has when its lookups run out.
  uses ledger
  at most 2 tool calls
  when it runs out: answer with what it has
  instructions: Look up what you are asked about in the ledger.

agent stops
  description: Looks entries up, and stops and says so when its lookups run out.
  uses ledger
  at most 2 tool calls
  when it runs out: stop and say so
  instructions: Look up what you are asked about in the ledger.

agent asks
  description: Looks entries up, and asks a person when its lookups run out.
  uses ledger
  limits:
    tool-calls-at-most: 2
    when-it-runs-out: ask-a-person
    asks: keep-looking
  instructions: Look up what you are asked about in the ledger.

agent both
  description: Looks entries up, two steps and two lookups at most, and asks a person.
  uses ledger
  limits:
    steps-at-most: 2
    tool-calls-at-most: 2
    when-it-runs-out: ask-a-person
    asks: keep-looking
  instructions: Look up what you are asked about in the ledger.

agent paced
  description: Looks entries up, three steps at most.
  uses ledger
  at most 3 steps
  when it runs out: answer with what it has
  instructions: Look up what you are asked about in the ledger.
