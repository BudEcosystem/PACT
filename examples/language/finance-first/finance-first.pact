# FINANCE FIRST, in the PACT language.
#
# This file and the folder `examples/kernel/finance-first` are the same
# workspace, written two ways. `pact show` prints the same document for both,
# and a test holds that (`the_same_workspace_written_two_ways`).
#
# What to read here: the two `listens for` lines, and the two `when` blocks
# inside the support agent. Nothing in `agent support` names the finance desk
# or the auditor — they asked to hear about its work, and they do.
workspace "Finance first"
  description: A support desk whose money questions go past the finance desk.

topic finance
  description: Money moving — refunds, invoices, credit, tax.
  # `tags` is exact: the billing tool is about to be used. `the-agent` is a
  # guess: the agent is given a `working-on` tool and says so itself.
  noticed-by: [tags, the-agent]

event refund-issued
  when billing/issue-refund has answered
  description: A refund has gone out.

agent support
  description: Answers customers about their orders.
  uses orders, billing
  at most 10 steps
  when it runs out: stop and say so

  when the agent has taken more than 6 steps
    called wrap-up
    description: A run that is taking long is told to finish with what it has.
    remind it: You have taken more than six steps on this request. Answer with what you have, and say plainly what you could not find out.

  # A judge reads what the customer wrote and answers this as a yes-or-no
  # question. It is a guess, so it may remind and may not stop.
  when it looks like the customer is angry or upset
    called upset-customer
    at: turn.run.started
    remind it: The customer is upset. Apologise once, plainly, before anything else.

  instructions
    Help the customer with their order. Look the order up before you answer.

agent finance-desk
  description: Knows the rules for refunds, invoices and tax.
  listens for topic finance: asked first
  instructions
    You are asked before money moves. Say what the rule is, and what is missing.
    A refund above 100 USD needs the order number and the reason.

agent auditor
  description: Keeps a note of every refund.
  listens for event refund-issued: told after
  instructions
    You are told when a refund has gone out. Write one line saying what it was for.

resource back-office
  resource-kind: mcp-server
  endpoint: host/back-office
  description: Where the billing and order systems are reached.

tool billing
  description: Invoices and refunds.
  connect: back-office
  about finance
  actions:
    look-up-invoice:
      description: Read one invoice.
      reads-only: yes
      takes:
        invoice: text
    issue-refund:
      description: Refund an order.
      spends-money: yes
      needs-a-person: yes
      same-request-key: order
      takes:
        order: text
        amount: money

tool orders
  description: Orders and deliveries.
  connect: back-office
  actions:
    look-up:
      description: Read one order.
      reads-only: yes
      takes:
        order: text
