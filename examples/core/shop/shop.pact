# A SHOP, WRITTEN IN PACT CORE (docs/100): a pattern and two desks made from
# it, a capability a program carries out, and a flow that reads what it was
# given by name, names a value, and states one.
workspace "Shop"
  description: Prices orders and decides refunds.
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

program add-up(amounts: list of number) gives total: number
  description: Adds a list of numbers.
  engine: wasm
  determinism: pure
  fuel:
    runs-for-at-most: 1s
    when-it-runs-out: stop-and-say-so

# A pattern, and two desks made from it.
define desk-for(domain: text, cap: money) as agent
  description: A desk that answers questions about <domain>.
  spends under <cap> a request
  when it runs out: stop and say so
  instructions: Answer questions about <domain>, briefly.

agent billing-desk is desk-for(domain: billing, cap: 0.10 USD)
agent tech-desk is desk-for(domain: technical problems, cap: 0.05 USD)

actor till
  description: Works out what an order comes to.
  uses orders
  at most 4 steps
  when it runs out: stop and say so

  can total(amounts: list of number) gives total: number
    by program add-up

  can judge(order: text, facts: text) gives decision: one of approved, declined
    by model
    instructions: Decide whether this order is refunded.

flow refund-one(order: text, amounts: list of number) gives decision: one of approved, declined, total: number, note: text
  description: Look an order up, total it, and decide.
  seen = orders/look(order: order)
  facts = seen.facts
  sum = till.total(amounts: amounts)
  ruled = till.judge(order: order, facts: facts)
  answer with decision: ruled.decision, total: sum.total, note: "decided by the till"
