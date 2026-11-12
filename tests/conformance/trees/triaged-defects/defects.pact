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
