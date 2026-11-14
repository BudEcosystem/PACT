# BOOKED VISITS — a workspace for the cases in tests/conformance/workflows.json
# about a run that something OUTSIDE it ended.
#
# A visit is booked in two systems and then a person confirms it. While that
# run is open the customer may cancel, and the cancellation arrives at a port
# with the same key (the visit). The run is then `cancelled`: never `stopped`,
# which is a run's own stages ending it.
workspace "Booked visits"
  description: A visit is booked in two systems, and a cancellation may arrive while it is.

resource back-office
  resource-kind: mcp-server
  endpoint: host/back-office
  description: Where the calendar and the customer files are reached.

tool calendar
  description: The clinic's calendar.
  connect: back-office
  actions:
    hold-slot:
      description: Hold a slot for a visit.
      undone-by: calendar/release-slot
      takes:
        visit: text
    release-slot:
      description: Give a held slot back.
      takes:
        visit: text

tool files
  description: The customers' files.
  connect: back-office
  actions:
    open-file:
      description: Open a file for a visit.
      undone-by: files/close-file
      takes:
        visit: text
    close-file:
      description: Close a file that was opened for a visit.
      takes:
        visit: text
    note:
      description: Write a line in the clinic's day book.
      takes:
        visit: text

question is-the-visit-confirmed
  description: Asked of the front desk once a visit is booked in both systems.
  says: Is this visit confirmed?
  answer:
    confirmed: yes or no
  shows: [input.visit]
  asked-of: [front-desk]
  answer-within: 1d

workflow book-visit
  description: Hold a slot, open a file, and have the front desk confirm the visit.
  takes visit: text, customer: text
  gives confirmed: yes or no
  hold = call calendar/hold-slot with visit: input.visit
  file = call files/open-file with visit: input.visit
  confirm = ask is-the-visit-confirmed
    then:
      declined: reply
  reply = answer with confirmed: confirm.confirmed

# What a port starts after it has ended a run. It takes the visit and not the
# customer, so it is handed the one and not the other.
workflow tell-the-clinic
  description: Write in the day book that a visit was called off.
  takes visit: text
  write = call files/note with visit: input.visit

port visit-booked
  description: A visit is booked.
  kind: event
  answers: book-visit
  same-conversation-when: [visit]

# The customer calls the visit off: the open run for that visit ends, what it
# did is taken back, and the clinic is told.
port visit-called-off
  description: The customer calls the visit off.
  kind: event
  answers: book-visit
  same-conversation-when: [visit]
  if-still-running: stop
  undo: yes
  then-run: tell-the-clinic

# The visit is withdrawn by the clinic itself, which keeps the slot and the
# file for whoever is booked in next: the run ends and nothing is undone.
port visit-withdrawn
  description: The clinic withdraws the visit and keeps what was set up for it.
  kind: event
  answers: book-visit
  same-conversation-when: [visit]
  if-still-running: stop

# A newer booking for the same visit replaces the open one.
port visit-booked-again
  description: The same visit is booked again, in place of the booking still open.
  kind: event
  answers: book-visit
  same-conversation-when: [visit]
  if-still-running: cancel-previous
  undo: yes
