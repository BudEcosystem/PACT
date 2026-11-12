# SORTED NOTES — a workspace for tests/conformance/workflows.json.
#
# A decision inside a loop, two ways: over a list of plain texts, where each
# text is what the sorter is given; and over a list of records, where the
# sorter is given the fields of the record it accepts and nothing else.
workspace "Sorted notes"
  description: Every note in a pile is put on a shelf.

shape letter
  id: text
  message: text
  secret: text

agent sorter
  description: Says which shelf a note belongs on.
  takes message: text
  gives shelf: one of bills, other
  instructions: Say which shelf.

workflow sort-texts
  description: Sort a pile of plain texts.
  takes notes: list of text
  every = for each item in input.notes
    limits:
      items-at-most: 5
      when-it-runs-out: stop-and-say-so
    where = decide
      says: Pick the shelf for this note.
      by:
        - { agent: sorter }
      if bills: done
      if other: done
  answer

workflow sort-letters
  description: Sort a pile of letters, each with more in it than the sorter reads.
  takes letters: list of letter, message: text
  every = for each item in input.letters
    identified-by: [id]
    limits:
      items-at-most: 5
      when-it-runs-out: stop-and-say-so
    where = decide
      says: Pick the shelf for this letter.
      by:
        - { agent: sorter }
      if bills: done
      if other: done
  answer
