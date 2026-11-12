# ROUTED DESK — a workspace for tests/conformance/workflows.json.
#
# The two workflows of `examples/language/help-centre`, with agents that no
# reaction covers: a decision by a written rule, then an agent, then a person;
# and one workflow calling another once for each item. Kept apart from that
# example so that what is compared here is the WORKFLOW — an agent a stage
# calls is an agent's run, under its own reactions, and those are held by
# reactions.json.
workspace "Routed desk"
  description: Sorts each message to the right desk.

agent billing-desk
  description: Answers billing questions.
  takes message: text
  gives reply: text
  instructions: Answer the billing question, briefly.

agent tech-desk
  description: Answers technical questions.
  takes message: text
  gives reply: text
  instructions: Say what to try first.

agent sorter
  description: Says which desk a message belongs to, or that it is not sure.
  takes message: text
  gives desk: one of billing, tech, out-of-scope, not-sure
  instructions: Say which desk should handle the message.

question which-desk
  description: Asked when neither the rules nor the sorter could place a message.
  says: Which desk should take this message?
  answer:
    desk: one of billing, tech, out-of-scope
  shows: [input.message]
  asked-of: [support-leads]
  answer-within: 1h

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
  gives replies: list of text, optional

  every = for each item in input.messages
    identified-by: [id]
    limits:
      items-at-most: 50
      when-it-runs-out: stop-and-say-so
    one = call route with message: item.text, channel: item.channel
  done-all = answer with replies: every.reply

shape message
  id: text
  text: text
  channel: text
