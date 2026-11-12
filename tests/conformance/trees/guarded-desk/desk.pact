# GUARDED DESK — a workspace for tests/conformance/reactions.json.
#
# Every kind of thing a reaction can do to a call, on signals that are exact:
# stop it, hold it until another agent has been heard (each different call),
# tell another agent once it has answered, and count it.
workspace "Guarded desk"
  description: A desk whose calls are guarded by reactions.

agent desk
  description: Sends mail and records payments.
  uses mail, bank
  reactions: [stop-large-payments]
  at most 8 steps
  when it runs out: stop and say so

  when the agent is about to call mail/send
    called check-each-mail
    every time
    consult reviewer

  when bank/pay has answered
    called note-each-payment
    every time
    tell ledger

  when the agent has called bank/balance more than 2 times
    called enough-looking
    remind it: You have looked at the balance three times. Use what you have.

  instructions
    Do what you are asked with the mail and bank tools.

agent reviewer
  description: Reads a message before it is sent.
  instructions: Say whether the message should go, and what to change.

agent ledger
  description: Keeps a note of every payment.
  instructions: Write one line saying what was paid.

# A reaction written out in full, because its signal reads an argument and no
# sentence says that.
reaction stop-large-payments
  description: A payment over 500 USD is not this desk's to make.
  at: step.tool.before
  when-this:
    - { tool: bank/pay, arg: amount, more-than: 500 USD }
  then:
    - stop: A payment over 500 USD is not this desk's to make.

resource office
  resource-kind: mcp-server
  endpoint: host/office
  description: Where the mail and bank systems are reached.

tool mail
  description: The desk's mailbox.
  connect: office
  actions:
    send:
      description: Send one message.
      takes:
        to: text
        body: text

tool bank
  description: The desk's bank account.
  connect: office
  actions:
    balance:
      description: Read the balance.
      reads-only: yes
    pay:
      description: Record one payment.
      spends-money: no
      takes:
        to: text
        amount: money
