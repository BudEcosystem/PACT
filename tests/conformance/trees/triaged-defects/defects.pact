# TRIAGED DEFECTS — a workspace for tests/conformance/workflows.json.
#
# What an agent that decides is given when the stage says so itself: `decide
# with ...` (`bind:` on a `decide`). Without it a deciding agent is given the
# workflow's input and the item and nothing an earlier stage found out, so an
# agent asked "which team takes a defect of the kind triage just named" was
# shown no kind at all.
workspace "Triaged defects"
  description: A defect is classified, and then somebody decides who takes it.

agent triager
  description: Says what kind of defect a report is about.
  takes report: text
  gives kind: one of engine, cabin, summary: text
  instructions: Say what kind of defect this is, and sum it up in a line.

agent assigner
  description: Says which team takes a defect of a given kind.
  takes kind: text, summary: text, urgency: text, optional
  gives team: one of powerplant, interiors
  instructions: Pick the team for this kind of defect.

agent shelver
  description: Says which shelf a note belongs on.
  takes note: text
  gives shelf: one of bills, other
  instructions: Say which shelf.

# The reporter guesses a `kind` too. What triage found is bound under the same
# name, and the bound one is what the assigner is given.
workflow fix-item
  description: Classify one defect report and pick the team that takes it.
  takes report: text, kind: text, urgency: text, secret: text
  gives team: text

  triage = call triager with report: input.report
  assign = decide with kind: triage.kind, summary: triage.summary
    by:
      - { agent: assigner }
    if powerplant: reply
    if interiors: reply
  reply = answer with team: assign.label

# A list of plain texts, and a sorter that calls its one input `note`. The
# stage says where the item goes; nothing guesses it.
workflow shelve
  description: Put every note in a pile on a shelf.
  takes notes: list of text
  every = for each item in input.notes
    limits:
      items-at-most: 5
      when-it-runs-out: stop-and-say-so
    where = decide with note: item
      by:
        - { agent: shelver }
      if bills: done
      if other: done
  answer

# A trained classifier and then a language model, on one decision with one
# `says:`. The classifier follows no instruction and is given the note as it
# is; the language model is given the instruction and then the note.
models
  version: 1
  models:
    note-classifier:
      description: A trained classifier that says which shelf a note belongs on.
      kind: decision
      served-by: [{runtime: systemone, endpoint: local}]

agent scorer
  description: Scores a note for a shelf.
  model: note-classifier
  takes message: text
  gives shelf: one of bills, other

agent reader
  description: Reads a note and says which shelf it belongs on.
  takes message: text
  gives shelf: one of bills, other
  instructions: Say which shelf.

workflow shelve-twice
  description: Put every note on a shelf, by a classifier and then by a reader.
  takes notes: list of text
  every = for each item in input.notes
    limits:
      items-at-most: 5
      at-once-at-most: 1
      when-it-runs-out: stop-and-say-so
    where = decide
      says: Pick the shelf for this note.
      by:
        - agent: scorer
          if-unsure-below: 85%
        - { agent: reader }
      if bills: done
      if other: done
  answer

# A written rule, then a second opinion on what the rule chose, then a person.
# The second opinion is asked even though the rule has decided; where it picks
# another label, or is not sure, nothing stands and the person is asked.
question which-shelf
  description: Asked when the rule and the second opinion do not agree.
  says: Which shelf does this note go on?
  answer:
    shelf: one of bills, other
  shows: [input.note]
  asked-of: [clerks]
  answer-within: 1h

question may-we-close
  description: Asked of both leads before a fix is closed.
  says: May this fix be closed?
  answer:
    close: yes or no
    note: text, optional
  shows: [input.report]
  asked-of: [lee, dana]
  answered-by: everyone
  answer-within: 1h

question may-the-team-close
  description: Asked of the leads' team before a fix is closed.
  says: May this fix be closed?
  answer:
    close: yes or no
  shows: [input.report]
  asked-of: [leads]
  answer-within: 1h

agent checker
  description: Gives a second opinion on which shelf a note belongs on.
  takes message: text
  gives shelf: one of bills, other, not-sure
  instructions: Say which shelf, or that you are not sure.

workflow shelve-checked
  description: Put one note on a shelf, and say who decided.
  takes note: text, folder: text
  gives shelf: text, decided: text, who: text, optional
  where = decide with message: input.note
    by:
      - rules:
          - when:
              - { value: input.folder, is: invoices }
            choose: bills
            because: Everything in the invoices folder is a bill.
      - agent: checker
        if-it-disagrees: go-on
      - { asks: which-shelf }
    if bills: reply
    if other: reply
  reply = answer with shelf: where.label, decided: where.decided-by, who: where.answered-by

# What every stage has besides its answer: how it ended, and for a loop how
# many rounds it took and whether what it was waiting for came to hold.
agent drafter
  description: Writes a draft and says whether it is good enough.
  takes brief: text
  gives draft: text, good: yes or no
  instructions: Write the draft. Say whether it is good enough to send.

workflow draft-until-good
  description: Draft until the draft is good, three times at most, and say how that went.
  takes brief: text
  gives rounds: whole number, ended: text, outcome: text
  polish = repeat at most 3 times
    until:
      - value: steps.write.good
        is: yes
    then:
      too-many-times: reply
    write = call drafter with brief: input.brief
  reply = answer with rounds: polish.rounds, ended: polish.ended, outcome: polish.outcome

# A workflow with no `answer` stage. It hands back nothing: what its last
# stage answered is the stage's, under its name, and not the workflow's.
workflow classify-only
  description: Classify one defect report, and hand nothing back.
  takes report: text
  triage = call triager with report: input.report

# Stages that wait for people. Who answered is a list, always, in the order
# their answers arrived.
#
# Everyone asked must answer: each of `asked-of:` answers separately, and one
# no is a no. Each may add a note; the stage's note is that of the answer that
# settled it (the first no, or the last yes needed).
workflow sign-off
  description: Ask both leads whether a fix may be closed, and say who answered.
  takes report: text
  gives close: yes or no, by: list of text, outcome: text, note: text, optional
  approve = ask may-we-close
    then:
      declined: reply
  reply = answer with close: approve.close, by: approve.answered-by, outcome: approve.outcome, note: approve.note

# A team is asked and the first answer decides. Who in the team answered is
# the host's to say, so the name kept is not the name that was asked.
workflow sign-off-by-the-team
  description: Ask the leads' team whether a fix may be closed, and say who answered.
  takes report: text
  gives close: yes or no, by: list of text
  approve = ask may-the-team-close
  reply = answer with close: approve.close, by: approve.answered-by

# A loop that is waiting for nothing: it runs its rounds and ends as any
# stage does. `too-many-times` is for one whose `until:` never came to hold.
workflow draft-three-times
  description: Draft three times, and say how that went.
  takes brief: text
  gives rounds: whole number, outcome: text, ended: text, optional
  polish = repeat at most 3 times
    then:
      too-many-times: gave-up
    write = call drafter with brief: input.brief
  reply = answer with rounds: polish.rounds, outcome: polish.outcome, ended: polish.ended
  gave-up = answer with rounds: polish.rounds, outcome: polish.outcome
