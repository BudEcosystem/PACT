# WHAT THE TEAM CAN REACH, and when a person is asked.

topic finance
  description: Money moving — refunds, invoices, credit, tax.

resource back-office
  resource-kind: mcp-server
  endpoint: host/back-office
  description: Where the billing system is reached.

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
      same-request-key: order
      takes:
        order: text
        amount: money

question may-we-refund
  description: Asked before a large refund goes out.
  says: This refund is over the desk's limit. May we send it?
  answer:
    approved: yes or no
  asked-of: [support-leads]
  answer-within: 4h
  if-nobody-answers: stop-and-say-so

question which-desk
  description: Asked when neither the rules nor the sorter could place a message.
  says: Which desk should take this message?
  answer:
    desk: one of billing, tech, out-of-scope
  shows: [input.message]
  asked-of: [support-leads]
  answer-within: 1h

policy approvals
  before billing/issue-refund, when amount is more than {use: large-refund}: ask may-we-refund, because a large refund is a management decision
