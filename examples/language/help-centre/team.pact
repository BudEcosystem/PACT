# THE TEAM. One pattern, and two desks made from it.

# A pattern: it never runs. `expects:` is what a desk made from it must fill
# in, and `<domain>` is where that goes.
agent desk
  description: A desk that answers questions about <domain>.
  base: yes
  expects:
    domain:
      shape: text
      help: what this desk answers questions about
    cap:
      shape: money
      help: the most one request may cost on this desk
  takes message: text
  gives reply: text
  spends under <cap> a request
  at most 8 steps
  when it runs out: stop and say so
  instructions
    Answer questions about <domain>, briefly. Say when you are not sure rather
    than guessing.

agent billing-desk
  based on desk with domain: billing, cap: 0.10 USD
  uses billing
  policy: approvals

  when the agent has taken more than 5 steps
    called wrap-up
    remind it: You have taken more than five steps. Answer with what you have.

agent tech-desk
  based on desk with domain: technical problems, cap: 0.05 USD

agent sorter
  description: Says which desk a message belongs to, or that it is not sure.
  takes message: text
  gives desk: one of billing, tech, out-of-scope, not-sure
  instructions
    Read the message and say which desk should handle it. Billing is money,
    invoices and refunds. Tech is anything broken. If you are not sure, say
    not-sure; a person will decide.

# Nothing in `billing-desk` names this agent. It asked to hear about finance
# work, and it is asked before that work goes on.
agent finance-desk
  description: Knows the rules for refunds, invoices and tax.
  listens for topic finance: asked first
  instructions
    You are asked before money moves. Say what the rule is, and what is missing.
