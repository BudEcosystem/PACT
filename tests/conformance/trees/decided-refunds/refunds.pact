# DECIDED REFUNDS — a workspace for tests/conformance/answers.json.
#
# What an agent's answer is held to. An agent says what it gives
# (`answers-with:`, written `gives` here), and may write rules of its own for
# an answer (`checked-by:`). A reply that would be the answer is held to both
# before it is one: asked for again with the reason, `checks-at-most:` times in
# all (2 when unwritten), and never handed back as it is.
workspace "Decided refunds"
  description: A desk that decides refunds, and says what it decided.

resource office
  resource-kind: mcp-server
  endpoint: host/office
  description: Where the orders are reached.

tool orders
  description: The order book.
  connect: office
  actions:
    look:
      description: Read one order.
      reads-only: yes
      takes:
        order: text

# A shape, and nothing else: two tries.
agent desk
  description: Decides a refund request.
  uses orders
  gives decision: one of approved, declined, amount: money, note: text, optional
  instructions: Decide the refund.

# One try.
agent strict
  description: Decides a refund request, and gets one try at saying so.
  gives decision: one of approved, declined
  checks-at-most: 1
  instructions: Decide the refund.

# A shape and a rule of the author's own, from one count.
agent ruled
  description: Decides a refund request and must say what happens to the money.
  gives decision: one of approved, declined
  checked-by:
    - must-contain: [refund]
      because: say what happens to the money
  instructions: Decide the refund.

# Nothing promised, so nothing held.
agent free
  description: Promises nothing about its answer.
  instructions: Help.

# The closing answer of a run that reached a limit is held like any other.
agent closes
  description: Looks orders up, and answers with what it has when it runs out.
  uses orders
  gives decision: one of approved, declined
  at most 1 tool calls
  when it runs out: answer with what it has
  instructions: Decide the refund.
