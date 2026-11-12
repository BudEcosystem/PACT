# THE FLOWS. A workflow is a function: it takes something, runs its steps in
# the order written, and gives something back. A step's name is a variable.

# One message to the right desk. `decide` picks a label; the steps beneath
# each `if` run for that label.
workflow route
  description: Send one message to the right desk.
  takes message: text, channel: text
  gives reply: text, optional

  where = decide
    by:
      - rules:
          - when:
              - { value: input.channel, is: invoices-mailbox }
            choose: billing
            because: Everything in the invoices mailbox is billing.
      - { agent: sorter }
      - { asks: which-desk }
    if billing
      bill = call billing-desk with message: input.message
      reply-bill = answer with reply: bill.reply
    if tech
      fix = call tech-desk with message: input.message
      reply-fix = answer with reply: fix.reply
    if out-of-scope
      decline = answer

# A whole inbox. This workflow calls the one above, once for each message.
workflow clear-inbox
  description: Route every message in an inbox.
  takes messages: list of message
  gives replies: text, optional

  every = for each item in input.messages
    identified-by: [id]
    limits:
      items-at-most: {use: messages-at-most}
      when-it-runs-out: stop-and-say-so
    one = call route with message: item.text, channel: item.channel
  done-all = answer with replies: every.reply

shape message
  id: text
  text: text
  channel: text
