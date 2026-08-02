# AC-1.5 — moderated usability trial protocol

**What this is.** A ready-to-run instrument for the one acceptance criterion no
amount of engineering can close: *can a non-technical domain expert build a
multi-agent system with PACT, unaided?*

**What it is not.** Evidence. Running it produces evidence; having it does not.
It exists because the alternative — an AI simulating a non-programmer and
reporting the result — would launder an assumption into a finding, and this
project's entire value rests on its claims being checkable.

---

## 1. Participants

**Recruit 5.** Nielsen's figure for finding ~85 % of usability problems, and the
smallest number that avoids one confident person carrying the result.

**Screen IN:** works with the domain (support, ops, analysis); comfortable
editing a spreadsheet or a config file when shown how.

**Screen OUT — this is the part prior work got wrong:** anyone who has written a
function in any language, used git beyond `clone`, or configured CI. The only
published study in this area recruited participants who *"generally all had
prior programming experience"*, which measures a different question entirely.

Ask directly: *"Have you ever written code that ran?"* One yes disqualifies.

---

## 2. Task

> Your company gives refunds. Build an assistant that decides refund requests.
> It should check the written policy, notice suspicious requests, and never
> promise a refund date. Then write down five examples of requests and what the
> right answer is, so you can tell whether it is working.

Deliberately phrased in the participant's language. It names no PACT concept —
not `agent`, not `eval`, not `contract`. If the format only works when the task
is phrased in its own vocabulary, it has failed.

**Materials:** a laptop with `pact` installed, an empty directory, the getting-
started page, and `pact check`. No templates. **No moderator help** beyond
§3.

**Time:** 60 minutes, hard stop.

---

## 3. Moderation

Think-aloud. The moderator answers **only**: *"What would you try next?"*

Log every instance of:
- **STUCK** — >2 min with no edit
- **HELP** — participant asks a question the materials should have answered
- **WRONG-MODEL** — states a belief about how it works that is false
- **ERROR-FAIL** — reads a diagnostic and still cannot act on it ← *the critical one*
- **ABANDON** — gives up on a sub-goal

`ERROR-FAIL` matters most because the entire no-code design rests on diagnostics
carrying a typeable fix. If a participant reads one and remains stuck, the
mechanism is broken regardless of what the automated tests say.

---

## 4. Pass criteria — fixed in advance

| # | Criterion | Bar |
|---|---|---|
| P1 | Produces a tree that `pact check` accepts | 4 of 5 |
| P2 | Tree contains ≥2 agents with distinct roles | 4 of 5 |
| P3 | Writes ≥3 eval cases with expected outcomes | 4 of 5 |
| P4 | Expresses the "never promise a date" rule somewhere enforceable | 3 of 5 |
| P5 | Zero `ERROR-FAIL` events | **5 of 5** |
| P6 | Completes within 60 min | 4 of 5 |

**AC-1.5 passes iff P1–P6 all hold.** Set before running, so the result cannot
be reinterpreted afterwards.

P5 is absolute: one participant who reads a diagnostic and cannot act on it
falsifies the design premise, whatever the completion rate.

---

## 5. Reporting

Report verbatim, including every quote where a participant was confused. A run
that fails is a finding, not an embarrassment — it is the only way to learn which
of the format's concepts do not survive contact with the intended user.

Publish alongside the automated necessary-conditions suite
(`crates/pact-cli/tests/authoring_surface.rs`), which currently shows: 26 files
for a complete system, all five common mistakes producing an actionable fix, no
programming jargon in any diagnostic, ≥90 % of fields carrying help text.

Those are necessary. This protocol tests whether they are sufficient.
