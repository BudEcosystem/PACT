# A PACT-language file beside the things that are files by nature.
#
# The handbook's documents are Markdown files in `knowledge/staff-handbook/
# documents/`, where they would be in any workspace. Everything else is here.
# `pact check examples/language/staff-desk` reads both as one workspace — the
# same one `examples/answers-from-documents` is.
workspace "Staff desk"
  description: Answers staff questions out of the handbook, and cites it.
  allow-egress: []

agent helpdesk "Staff desk"
  description: Answers questions about leave, expenses and working hours.
  uses staff-handbook
  instructions
    Answer only from the staff handbook, and say which part of it you used.

    If the handbook does not cover what somebody asked, say so and tell them to
    email the people team. Do not guess, and do not fill a gap from what you happen
    to know about other companies — the handbook is the only thing that is true
    here.

knowledge staff-handbook
  description: The staff handbook everyone asks about.
  looked-up-by: words
  passages-at-most: 3
  must-cite: yes
  use-when: somebody asks about leave, expenses, working hours or notice periods
  do-not-use-when: somebody asks about their own pay or a personal grievance
  if-unsure: say the handbook does not cover it and point them at the people team
