# A REFUND DESK, WRITTEN IN PACT CORE (docs/100).
#
# One actor with three capabilities. What is beneath each `can` says who
# carries it out: `by model` is a model deciding; statements are steps written
# out, the same every time.
workspace "Refund desk in Core"
  description: One actor decides refunds; what a model decides and what is written out are told apart on the page.
  allow-egress: []

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

tool payments
  description: Where money is sent back.
  connect: office
  actions:
    refund:
      description: Refund one order.
      spends-money: yes
      needs-a-person: yes
      same-request-key: order
      takes:
        order: text
        amount: money

# The one agent here that may pay. A cell it writes may call `payments/refund`;
# a cell `desk` writes may not, because `desk` was never given it.
agent cashier(order: text) gives paid: yes or no
  description: Pays a refund that has been approved.
  uses payments
  # How its answer is asked for and read: in the instructions, and read back
  # out of what the model wrote.
  answers-with-mode: prompted
  # Its Allowance, written out as settings. The money it may spend comes from
  # whoever started the run, never above the figure here, and is counted over
  # a day and not over one run.
  run-inputs:
    budget: money
  limits:
    steps-at-most: 4
    cost-per-request-under: 0.05 USD
    cost-per-request-from: run-inputs.budget
    counted-per: run
    resets-every: 1 day
    when-it-runs-out: stop-and-say-so
  instructions: Refund the order you are given, once.

shape verdict
  decision: one of approved, declined
  reason: text

actor desk
  description: Decides refund requests.
  uses orders
  at most 6 steps
  when it runs out: stop and say so

  can judge(order: text, facts: text) gives decision: one of approved, declined, reason: text
    by model
    instructions: Decide whether this order is refunded, from the facts given. Say why in one sentence.

  can summarise(verdicts: list of verdict) gives summary: text
    by model
    instructions: Say in one sentence how many were approved and how many declined.

  can decide-one(order: text) gives decision: text, reason: text
    seen = orders/look(order: input.order)
    ruled = desk.judge(order: input.order, facts: seen.facts)
    answer with decision: ruled.decision, reason: ruled.reason

# A function: what it takes and gives is on the line that names it, and it is
# called like one.
flow decide-all(orders: list of text) gives summary: text, verdicts: list of verdict
  description: Decide every order in a list, five at a time, and sum up.
  each = for each item in input.orders
    limits:
      items-at-most: 50
      at-once-at-most: 5
      when-it-runs-out: stop-and-say-so
    one = desk.decide-one(order: item)
  told = desk.summarise(verdicts: each.items)
  answer with summary: told.summary, verdicts: each.items
