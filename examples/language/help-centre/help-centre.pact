# HELP CENTRE — one workspace in four files.
#
# Every `.pact` file at the top of a folder is read as part of one workspace,
# so a workspace can be split by subject:
#
#   help-centre.pact   the workspace, its shared figures, and how it learns
#   team.pact          the agents: one pattern, two desks made from it, a sorter
#   tools.pact         what they can reach, and when a person is asked
#   flows.pact         two workflows, one calling the other
#
# `pact check examples/language/help-centre` reads all four.
workspace "Help centre"
  description: Sorts each message to the right desk, with money questions past the finance desk.
  owner: support

# A figure with a name. `{use: large-refund}` stands wherever it belongs, so
# raising it is one edit.
let large-refund = 200 USD

let messages-at-most = 50

# What the system may do about getting better at its job. `propose-only`:
# it suggests, a person decides, and nothing changes until somebody says yes.
learning
  enabled: propose-only
  needs-a-person-to-approve: [tools, permissions, team, limits, evals, policy-clauses]
  keep-only-if: a-person-approves-it
  review: manual
