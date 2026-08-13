//! The **LoadReport** — LOAD-14's machine-readable account of what a load
//! found, and the first entry it carries: **every wait the tree can produce.**
//!
//! # Why a wait needs an entry of its own
//!
//! §7.14 makes a deadline a field of the durable record: a question says
//! `answer-within: 30m`, the record carries it, and `Suspension.expired(now)`
//! turns it into an outcome. But `expired` is evaluated on exactly one path —
//! when a caller re-enters the run with an answer
//! (`adapters/python/src/pact_adapters/harness.py:565`) — against a `now` the
//! caller supplies. **Nothing schedules the moment it is read.** So an author's
//! `answer-within: 30m` becomes an outcome only when somebody comes back, and a
//! parked run nobody comes back to waits exactly as long as Eve's does, which is
//! forever.
//!
//! That division of labour is correct and deliberate — PACT is a specification
//! and not a server (NG1), so it has no clock and no process to run one on. What
//! was missing is the other half: an obligation written down somewhere a runtime
//! author can comply with, and a list they can comply *against*. §9.4 G14 now
//! states the obligation. This module is the list.
//!
//! # What is here and what is the runtime's
//!
//! | PACT supplies | the runtime supplies |
//! |---|---|
//! | that this run can stop, and why (`reason`) | the clock |
//! | how long it may wait ([`Wait::deadline_ms`]) | the timer, and the wakeup |
//! | what to do when the time is up ([`Wait::if_nobody_answers`]) | performing it |
//! | who may answer, and who it escalates to | reaching those people |
//!
//! A runtime that reads [`LoadReport::wake_ups`] and sets one timer per entry
//! has complied. One that does not will park a run and never look at it again —
//! which is not a smaller version of the feature, it is Eve's behaviour with
//! extra fields.
//!
//! # Why it is derived rather than written
//!
//! There is no `pauses/` kind in the schema (WAIT-2): everything a wait needs is
//! already what a `question` is. So this reads the six lines that can stop a run
//! straight out of the loaded document, exactly as
//! `pact_adapters.suspension._named_questions` does on the executing side. A
//! hand-maintained list would be a copy of the tree that stops being true the
//! first time somebody edits a question — which is the whole reason the test for
//! this asserts against the worked example's own files rather than against a
//! literal.

use camino::Utf8PathBuf;
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Entry, Map, Node};

/// Why a run stopped. §7.14 WAIT-1's closed set, plus the `x-` escape.
///
/// These strings are also the ones the executing side parks under
/// (`pact_adapters/suspension.py`'s `REASONS`), and they have to match: the
/// correlation key that lets an answer find its way home is derived from the
/// reason, so a report naming `needs-approval` for a wait the harness parks as
/// something else would send a scheduler's wakeup to a key nothing is waiting
/// on. §7.14 WAIT-1 is the normative list; these two are its readers.
pub const NEEDS_APPROVAL: &str = "needs-approval";
pub const NEEDS_PERMISSION: &str = "needs-permission";
pub const OUT_OF_BUDGET: &str = "out-of-budget";
pub const CONTEXT_TOO_LONG: &str = "context-too-long";
/// A `does: ask-someone` stage of an authored loop (LOOP-5). Registered through
/// the `x-` escape rather than by widening the closed list, which is where the
/// harness put it too.
pub const ASKED_A_PERSON: &str = "x-asked-a-person";

/// One wait the tree can produce: what stops, why, and when a runtime must act.
///
/// Everything here is read off the author's own lines. Nothing is minted, and
/// nothing is defaulted into existence — a wait with no deadline reports no
/// deadline rather than an invented one, because an invented deadline is a
/// governance decision taken on the author's behalf.
#[derive(Debug, Clone, PartialEq)]
pub struct Wait {
    /// §7.14 WAIT-1's reason. The same string the durable record parks under.
    pub reason: &'static str,
    /// Whose run stops. A wait belongs to a run, and a run belongs to an agent.
    pub agent: String,
    /// The entry in `questions/` the author named.
    pub question: String,
    /// The line that can stop the run — `limits.asks`, `teamwork.asks`, a
    /// policy rule's `question:`. Named so a person told "this run is waiting"
    /// can open the file that decided it would.
    pub declared_at: Span,
    /// `answer-within:` exactly as the author typed it. Empty when they wrote
    /// none.
    pub answer_within: String,
    /// The same, in milliseconds. `None` means **nothing will ever wake this
    /// wait** — there is no time for it to run out of, so
    /// [`Wait::if_nobody_answers`] can never happen.
    pub deadline_ms: Option<u64>,
    /// `if-nobody-answers:` — what the runtime must do at the deadline. Never
    /// "approve": §7.14 WAIT-4 leaves nowhere to write it.
    pub if_nobody_answers: String,
    /// `asked-of:` — who may answer. Naming nobody means nobody can.
    pub asked_of: Vec<String>,
    /// `escalates-to:` — who it goes to next, when the action is `escalate`.
    /// Carried because a runtime told only to escalate has nobody to escalate
    /// to, and would have to guess.
    pub escalates_to: Vec<String>,
}

impl Wait {
    /// Is this a wait a scheduler can set a timer for?
    ///
    /// False is not a mistake by itself — WAIT-8 makes waiting forever what you
    /// get when you write nothing. It is a mistake only when the author *did*
    /// write something for the timeout to do, which is what
    /// `loader/wait-with-no-deadline` reports.
    pub fn wakes(&self) -> bool {
        self.deadline_ms.is_some()
    }
}

/// What the load found. LOAD-14 lists ten entries this will eventually carry
/// (files consumed, files suppressed with the pattern that suppressed them,
/// migrations applied, and so on); [`LoadReport::waits`] is the first of them to
/// exist, because it is the one a runtime cannot comply with §9.4 G14 without.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct LoadReport {
    /// Every wait the tree can produce, in document order: agents in the order
    /// they load, and within an agent, the order §7.14 WAIT-2's table lists.
    /// Deterministic, because a report two machines disagree about is not a
    /// contract.
    pub waits: Vec<Wait>,
}

impl LoadReport {
    /// Read the report out of a loaded document.
    ///
    /// Takes the document rather than being returned by [`crate::Loader::load`]
    /// because it is computed *from* the document and nothing else — no second
    /// pass over the filesystem, no network, no author code (LOAD's purity rule
    /// holds here as everywhere).
    pub fn of(document: &Node, diags: &mut Diagnostics) -> LoadReport {
        let questions = document.get("questions");
        let mut waits = Vec::new();
        //: What is known about each question ACROSS every line that puts it.
        //:
        //: Gathered per question and not per binding, for two reasons that turn
        //: out to be the same reason. A question put at a budget park in one
        //: agent and at a tool approval in another has an open `shows:`
        //: vocabulary through the second even though the first closes it. And a
        //: question `policies/approvals.yaml` names three times is ONE file with
        //: one mistake in it — reporting a missing `answer-within:` once per
        //: line that reaches it gives the author three things to fix and one
        //: thing to change, which is the noise `_named_questions` is deduplicated
        //: to avoid on the executing side.
        let mut asked: std::collections::BTreeMap<String, Asked> =
            std::collections::BTreeMap::new();

        let Some(agents) = document.get("agents").and_then(Node::as_map) else {
            return LoadReport { waits };
        };

        for (agent_name, agent) in agents {
            // An agent naming a policy, loop or context policy that resolves to
            // nothing has parks this walk cannot see, so nothing may be concluded
            // from what is missing. The reference check reports the real mistake
            // at the line the author typed.
            let dangling = ["policy", "loop", "context-policy"].iter().any(|field| {
                agent
                    .node
                    .get(field)
                    .and_then(Node::as_str)
                    .map(str::trim)
                    .is_some_and(|name| {
                        !name.is_empty()
                            && named_in(document, collection_for(field), &agent.node, field)
                                .is_none()
                    })
            });
            for (reason, question, declared_at, shows) in asking_lines(document, &agent.node) {
                let entry = match questions.and_then(|q| q.get(&question)) {
                    Some(entry) => entry,
                    // The one name that is not in `questions/` and is still real:
                    // the question PACT ships for `needs-a-person: yes` (F17).
                    // Read from `spec/questions/is-this-ok.yaml`, so a gate
                    // written the short way carries the same deadline, audience
                    // and timeout action onto this list as one written the long
                    // way — which is the whole claim the shorthand makes, and
                    // the list a scheduler is obliged to walk is where it is
                    // either true or not.
                    None if question == crate::approvals::SHIPPED_QUESTION => {
                        crate::approvals::shipped_question()
                    }
                    // A name with no `questions/` entry behind it is already
                    // reported where the author is, by REF-1's reference check
                    // (§7.12). A second diagnostic saying the same thing in
                    // other words would just be two things to fix for one
                    // mistake.
                    None => continue,
                };
                let seen = asked.entry(question.clone()).or_default();
                // Per BINDING, not per question. `check_shows` used to exempt a
                // whole question the moment ANY binding of it was an action park,
                // so the worked example's `if-someone-fails: ask-a-person` put a
                // decision to a person with no facts at all: `is-this-ok` is
                // bound both by a policy rule (open) and by `teamwork.asks`
                // (closed), and its `shows: [amount, order-number]` was never
                // held against the teammate park. The run rendered *"Please check
                // this before it happens."* and nothing else — not who failed,
                // not why, not who did answer.
                seen.incomplete |= dangling;
                let open = matches!(shows, Shown::Anything);
                let names = match shows {
                    Shown::Anything => Vec::new(),
                    Shown::These(names) => names,
                };
                seen.bindings.push(Binding {
                    open,
                    names: names.clone(),
                });
                if open {
                    seen.open = true;
                } else {
                    seen.names.extend(names);
                }
                if seen.first.is_none() {
                    seen.first = Some(declared_at.clone());
                }
                waits.push(read_wait(reason, agent_name, &question, declared_at, entry));
            }
        }

        for (question, seen) in &asked {
            if let Some(entry) = questions.and_then(|q| q.get(question)) {
                check_deadline(question, entry, seen, diags);
                check_shows(question, entry, seen, diags);
                check_somebody_can_answer(question, entry, seen, diags);
                check_nobody_approves_their_own_work(question, entry, document, diags);
            }
        }

        LoadReport { waits }
    }

    /// The waits a scheduler sets a timer for.
    ///
    /// This is the list §9.4 G14 is about: a runtime that walks it, times each
    /// entry from the moment the run parked, and performs
    /// [`Wait::if_nobody_answers`] when the time is up has met the obligation.
    /// A wait with no deadline is absent from it — deliberately, because there
    /// is no moment for a scheduler to wake at.
    pub fn wake_ups(&self) -> impl Iterator<Item = &Wait> {
        self.waits.iter().filter(|w| w.wakes())
    }

    /// The report as data, for a runtime that is not written in Rust (AC-7.1,
    /// §9.4 G13). Keys are the author's spellings, so a person reading this
    /// output and a person reading the YAML are reading the same words.
    pub fn to_json(&self) -> serde_json::Value {
        serde_json::json!({
            "waits": self.waits.iter().map(|w| serde_json::json!({
                "reason": w.reason,
                "agent": w.agent,
                "question": w.question,
                "declared-at": w.declared_at.to_string(),
                "answer-within": w.answer_within,
                "deadline-ms": w.deadline_ms,
                "if-nobody-answers": w.if_nobody_answers,
                "asked-of": w.asked_of,
                "escalates-to": w.escalates_to,
                // WHETHER A SCHEDULER CAN TIME THIS ONE, said rather than left to
                // be re-derived. `wakes()` and `wake_ups()` were the only two
                // functions in this crate with no caller outside a test — and the
                // reason was here: the JSON handed a runtime every wait and no way
                // to tell which of them has a moment to wake at, so a consumer
                // complying with §9.4 G14 had to reimplement the rule and could
                // reimplement it differently.
                "wakes": w.wakes(),
            })).collect::<Vec<_>>(),
            // And the filtered list itself, because G14's obligation is stated
            // over exactly this set: *"a runtime that walks it, times each entry
            // from the moment the run parked, and performs `if_nobody_answers`
            // when the time is up has met the obligation."* A consumer reading
            // this key has met it without writing a filter.
            "wake-ups": self.wake_ups().map(|w| w.question.clone()).collect::<Vec<_>>()
        })
    }
}

// ────────────────────────────────────────────── what a park can put on the screen
//
// `shows:` names values to put in front of the person, and where the run stopped
// decides which names mean anything. Two shapes, and the difference is the whole
// of the check below.
//
// Every park OTHER than an action offers a small closed list, written here and in
// the schema's help for `question.shows` and nowhere else. These are `shown.py`'s
// functions, one tuple per function, and they have to stay in step with it: a
// name in one and not the other is a name the author is told works and never
// sees.
//
// A park about a pending ACTION used to be `OPEN` — no list, so no name could be
// refused. That was true when it was written and stopped being true when `takes:`
// landed: the action now says what it is given, so the list is not missing, it
// was only never asked for. And the two parks it left unchecked are the two that
// MOVE MONEY. Measured on the worked example with `shows: [banana]` in each file:
// `questions/keep-going.yaml` and `questions/too-long-to-send.yaml` warned, while
// `questions/is-this-ok.yaml` — the approval before a refund — and
// `questions/may-we-connect.yaml` — the consent to spend over a connection —
// both printed *"OK — … loaded cleanly"* and exited 0. So an author named a value
// for the approver to see and the approver silently saw nothing.

/// What ONE park can put in front of the person.
///
/// [`Shown::Anything`] is not "everything" — it is *"PACT has no list here"*, and
/// it is deliberately still reachable: an action with no `takes:` block, or a
/// rule naming a tool this document does not have. Concluding from an incomplete
/// picture is how a correct `shows:` line comes to be refused, and refusing a
/// legitimate name is worse than the silence this check exists to end.
enum Shown {
    /// No list to hold a name against, so no name may be called wrong.
    Anything,
    /// Exactly these, and a name outside them is shown to nobody.
    These(Vec<String>),
}

impl Shown {
    /// One of the closed vocabularies below.
    fn of(names: &[&str]) -> Shown {
        Shown::These(names.iter().map(|s| s.to_string()).collect())
    }
}

/// `out-of-budget` — `shown.spent`.
const WHEN_A_CEILING_STOPS_IT: &[&str] = &[
    "spent-so-far",
    "steps-taken",
    "tool-calls-made",
    "time-spent",
    "tokens-used",
    "which-limit",
];

/// `context-too-long` — `shown.tidying`.
const WHEN_IT_IS_TOO_LONG: &[&str] = &["how-much-over", "what-was-tried", "how-long-it-is"];

/// `needs-approval` from `teamwork` — `shown.teammate`.
const WHEN_A_TEAMMATE_COULD_NOT: &[&str] = &[
    "who-could-not-answer",
    "why-they-could-not",
    "who-did-answer",
];

/// `x-asked-a-person` — `shown.a_stage`.
const WHEN_A_STAGE_ASKS: &[&str] = &["the-stage", "what-the-stage-said"];

/// One place this question is put, and what THAT park can show.
struct Binding {
    open: bool,
    names: Vec<String>,
}

/// What every line that puts one question knows about it, gathered.
#[derive(Default)]
struct Asked {
    /// True when at least one of those parks is about an action, whose argument
    /// names PACT has no list of.
    open: bool,
    /// Every value the closed parks among them can put on the screen.
    names: std::collections::BTreeSet<String>,
    /// Each park separately, because a `shows:` name is legitimate where it is
    /// supplied and dropped in silence where it is not, and "some park can
    /// supply it" is not the question a person standing in front of an empty
    /// screen is asking.
    bindings: Vec<Binding>,
    /// The first line that can start this wait — where a diagnostic about the
    /// question points the reader back to.
    first: Option<Span>,
    /// True when this agent named a policy, loop or context policy that resolves
    /// to nothing, so the set of parks gathered here is incomplete and no
    /// conclusion may be drawn from its absences.
    incomplete: bool,
}

/// What a call to ONE action can carry, as the model is shown it.
///
/// `takes:` — the block the author already writes to say what the action is
/// given — plus `action` itself, because `ir._takes` declares
/// `action: one of read-ticket, reply` on every tool with an `actions:` block, so
/// the call carries it and a question may legitimately show which one this was.
///
/// [`Shown::Anything`] wherever there is nothing to hold a name against: a tool
/// or an action this document does not have, or an action that never says what
/// it is given. The first of those is a real mistake and is reported where the
/// author is, by `approvals::check`, at the line they typed — saying it a second
/// time here in other words would be two things to fix for one mistake.
fn what_a_call_carries(document: &Node, tool: &str, action: &str) -> Shown {
    let Some(actions) = document
        .get("tools")
        .and_then(|t| t.get(tool))
        .and_then(|t| t.get("actions"))
        .and_then(Node::as_map)
    else {
        return Shown::Anything;
    };
    // An empty action means "every one of them". A policy rule may not be
    // written that way — `loader/rule-names-no-action` refuses the spelling —
    // but a CONNECTION consent has no `when:` at all and stops every call to the
    // tool, so a call under it can carry any action's arguments.
    let wanted: Vec<&Entry> = if action.is_empty() {
        actions.values().collect()
    } else {
        match actions.get(action) {
            Some(one) => vec![one],
            None => return Shown::Anything,
        }
    };
    let mut names: std::collections::BTreeSet<String> = Default::default();
    for entry in wanted {
        let Some(takes) = entry.node.get("takes").and_then(Node::as_map) else {
            return Shown::Anything;
        };
        names.extend(takes.keys().cloned());
    }
    if names.is_empty() {
        return Shown::Anything;
    }
    names.insert("action".to_string());
    Shown::These(names.into_iter().collect())
}

/// The same, for the actions ONE approval rule is about.
///
/// The union over every `<tool>/<action>` its `when:` names, because a rule may
/// name several and the run stops at whichever one the model actually called. One
/// unresolvable name makes the whole rule [`Shown::Anything`] — a picture with a
/// hole in it is not a list to refuse an author's line against.
fn what_the_rule_is_about(document: &Node, rule: &Node) -> Shown {
    let Some(whens) = rule.get("when").and_then(Node::as_list) else {
        return Shown::Anything;
    };
    let mut names: std::collections::BTreeSet<String> = Default::default();
    let mut resolved = false;
    for when in whens {
        let Some(written) = when.get("tool").and_then(Node::as_str).map(str::trim) else {
            continue;
        };
        let (tool, action) = match written.split_once('/') {
            Some((t, a)) => (t.trim(), a.trim()),
            None => (written, ""),
        };
        match what_a_call_carries(document, tool, action) {
            Shown::Anything => return Shown::Anything,
            Shown::These(more) => {
                resolved = true;
                names.extend(more);
            }
        }
    }
    if !resolved {
        return Shown::Anything;
    }
    Shown::These(names.into_iter().collect())
}

/// Every `(reason, question, where the line is, what that park can show)` this
/// agent could stop at.
///
/// One place, mirroring WAIT-2's table row for row, so "which lines can stop a
/// run?" stays a list somebody can read rather than a search through a harness.
///
/// It differs from `suspension._named_questions` in one deliberate way: that one
/// keeps the **first** rule per reason, because a running wait has exactly one
/// deadline governing it. A report may not do that. A policy with three
/// `ask-a-person` rules can park showing any of their questions, and a scheduler
/// told only about the first has no timer for the other two.
fn asking_lines(document: &Node, agent: &Node) -> Vec<(&'static str, String, Span, Shown)> {
    let mut found = Vec::new();

    // out-of-budget — `limits.asks`
    if let Some(limits) = agent.get("limits")
        && says(limits, "when-it-runs-out", "ask-a-person")
        && let Some((name, span)) = named(limits, "asks")
    {
        found.push((
            OUT_OF_BUDGET,
            name,
            span,
            Shown::of(WHEN_A_CEILING_STOPS_IT),
        ));
    }

    // needs-approval — every `ask-a-person[].question` of every policy that
    // covers this agent. It read only the policy the agent NAMES, so a policy
    // saying `applies-to: every-agent` produced no wait at all for the two
    // agents that had not named it, and `pact waits` — the list §9.4 G14
    // obliges a runtime to walk — was short by every one of them.
    let named_policy = agent
        .get("policy")
        .and_then(Node::as_str)
        .unwrap_or("")
        .trim();
    if let Some(all) = document.get("policies").and_then(Node::as_map) {
        for (key, entry) in all {
            if !crate::money::covers(&entry.node, key, named_policy) {
                continue;
            }
            let Some(rules) = entry.node.get("ask-a-person").and_then(Node::as_list) else {
                continue;
            };
            for rule in rules {
                if let Some((name, span)) = named(rule, "question") {
                    // The action's own `takes:`, not `OPEN`. This is the park
                    // that stops money, and it was the one with no check.
                    found.push((
                        NEEDS_APPROVAL,
                        name,
                        span,
                        what_the_rule_is_about(document, rule),
                    ));
                }
            }
        }
    }

    // needs-approval — `tools.<t>.actions.<a>.needs-a-person` (F17), the gate
    // written in one line.
    //
    // It is on this list for the same reason the rules above it are: §9.4 G14
    // obliges a runtime to hold a timer for every outstanding wait, and a gate
    // it cannot see is a run that parks and is never looked at again. A wait
    // written the short way therefore has to reach a scheduler indistinguishable
    // from one written the long way — same reason, same deadline, same timeout
    // action, and a `declared-at` pointing at the line the author really typed,
    // which here is the `needs-a-person:` line in the tool's own file.
    //
    // Bound through `uses:`, not through `policies:`. The long form asks which
    // agents a policy covers; this one asks which agents can reach the tool,
    // which needs no line from the author and is strictly narrower.
    for gated in crate::approvals::desugared_for(document, agent) {
        // `Desugared::shows` is already the action's `takes:` — the short form
        // reads them off the action because the action says what it is given —
        // so this park has had a list all along and only needed to say so.
        let shows = if gated.shows.is_empty() {
            Shown::Anything
        } else {
            Shown::These(gated.shows.clone())
        };
        found.push((
            NEEDS_APPROVAL,
            crate::approvals::SHIPPED_QUESTION.to_string(),
            gated.declared_at,
            shows,
        ));
    }

    // needs-approval — `teamwork.asks`
    if let Some(team) = agent.get("teamwork")
        && says(team, "if-someone-fails", "ask-a-person")
        && let Some((name, span)) = named(team, "asks")
    {
        found.push((
            NEEDS_APPROVAL,
            name,
            span,
            Shown::of(WHEN_A_TEAMMATE_COULD_NOT),
        ));
    }

    // needs-permission — `resources.<server>.asks-to-connect`, reached the way a
    // RUN reaches it: the agent's `uses:` names a TOOL, the tool's `connect:`
    // names a server, and the server carries the question.
    //
    // `uses:` cannot name a resource at all — the schema says
    // `names: [tools, skills]` — so looking a resource up under a name written
    // there found one only when a tool and a server happened to be spelled the
    // same. The worked example spelled both `payments`, which is exactly why the
    // coincidence survived: rename the tool alone and the connection wait
    // vanished off this list while the harness went on parking for it.
    // `suspension.connections_needing_permission` walks this chain on the
    // executing side, and the two have to name the same waits or a scheduler
    // holds a timer for a park that cannot happen and none for the park that can.
    if let Some(resources) = document.get("resources").and_then(Node::as_map) {
        let tools = document.get("tools");
        // Sorted, because the executing side enumerates `uses:` sorted. Two
        // lists in two languages that disagree about ORDER are two lists a
        // runtime author has to reconcile by hand.
        let mut reachable = strings(agent.get("uses"));
        reachable.sort();
        for used in reachable {
            // `connect:` is ONE name now, not a map of them. It was
            // `map of text` with no `names:`, so `mcp: paymnets-server` loaded
            // clean and this whole entry vanished off the list a scheduler is
            // obliged to walk — a human consent gate on money, gone in silence.
            // One key whose name was never checked is two mistakes: the
            // unchecked name, and a `mcp:` label nothing ever read.
            let Some(server) = tools
                .and_then(|t| t.get(&used))
                .and_then(|t| t.get("connect"))
                .and_then(Node::as_str)
                .map(str::trim)
            else {
                continue; // a skill, or a tool that connects to nothing
            };
            if let Some(entry) = resources.get(server)
                && let Some((name, span)) = named(&entry.node, "asks-to-connect")
            {
                // One wait per tool. A run stops once before it uses that tool,
                // whatever the tool is wired to underneath.
                //
                // No `when:` anywhere, so this stops EVERY call to the tool and
                // the values on the screen are whichever action the model
                // reached for — hence every action's `takes:`, not one's.
                found.push((
                    NEEDS_PERMISSION,
                    name,
                    span,
                    what_a_call_carries(document, &used, ""),
                ));
            }
        }
    }

    // context-too-long — `context-policies.<the agent's>.asks` (CTX-9)
    if let Some(tidying) = named_in(document, "context-policies", agent, "context-policy")
        && says(tidying, "if-it-still-does-not-fit", "ask-a-person")
        && let Some((name, span)) = named(tidying, "asks")
    {
        found.push((CONTEXT_TOO_LONG, name, span, Shown::of(WHEN_IT_IS_TOO_LONG)));
    }

    // x-asked-a-person — `loops.<the agent's>.steps.<stage>.asks` (LOOP-5).
    //
    // Only the loop as written in this workspace is read. A `based-on:` shape
    // can add inherited stages, and neither shape PACT ships (`spec/loops/`)
    // contains a `does: ask-someone` stage, so inheritance cannot introduce a
    // wait today. If one is ever added there, this needs the library too.
    if let Some(steps) = named_in(document, "loops", agent, "loop")
        .and_then(|l| l.get("steps"))
        .and_then(Node::as_map)
    {
        for stage in steps.values() {
            if says(&stage.node, "does", "ask-someone")
                && let Some((name, span)) = named(&stage.node, "asks")
            {
                found.push((ASKED_A_PERSON, name, span, Shown::of(WHEN_A_STAGE_ASKS)));
            }
        }
    }

    found
}

/// A `shows:` name that nothing where this question is asked can put on the
/// screen.
///
/// The same class of defect `shown.py` was written to fix, one letter away:
/// `shows: [spent-so-far, steps-taken]` was a line the author wrote that reached
/// nobody, and `shows: [spent-so-fa]` still is — `Question.about_call` filters
/// with `if k in args`, so an unrecognised name simply vanishes, at check time
/// and again at run time, with nothing anywhere saying so.
///
/// Every park with a list to hold a name against is checked, and a park about a
/// pending action now has one: the `takes:` block the author wrote on it. Until
/// it did, the two parks that MOVE MONEY were the two exempt from this — an
/// approval before a refund and the consent to spend over a connection both took
/// `shows: [banana]` in silence.
///
/// What is still exempt is genuinely listless: an action with no `takes:`, a rule
/// naming a tool this document does not have, a question put somewhere PACT has
/// no vocabulary for. Refusing `order-number` because it is not in a table would
/// be worse than the silence, so the absence of a list is never read as an empty
/// one — see [`Shown::Anything`].
fn check_shows(question: &str, q: &Node, asked: &Asked, diags: &mut Diagnostics) {
    // A tree with a broken reference has an incomplete set of parks, so an
    // absence here proves nothing. Reproduced: misspelling `policy: approvals`
    // made this warn twice about `questions/is-this-ok.yaml`, a file with
    // nothing wrong in it, and following the fix would have broken it.
    if asked.incomplete {
        return;
    }
    let Some(shows) = q.get("shows") else { return };
    let written: Vec<&Node> = match shows.as_list() {
        Some(items) => items.iter().collect(),
        None => vec![shows],
    };
    // ── the name nothing anywhere supplies ───────────────────────────────────
    //
    // The original rule, and still the right one for a misspelling:
    // `shows: [spent-so-fa]` is a line the author wrote that reaches nobody,
    // because `Question.about_call` filters with `if k in args` and an
    // unrecognised name simply vanishes. Silent when ANY park putting this
    // question is about an action, whose argument names PACT has no list of.
    if !asked.open && !asked.names.is_empty() {
        let allowed: Vec<&str> = asked.names.iter().map(String::as_str).collect();
        for item in &written {
            let Some(name) = item.as_str().map(str::trim) else {
                continue;
            };
            if name.is_empty() || asked.names.contains(name) {
                continue;
            }
            diags.push(Diagnostic::warning(
                "loader/shows-nothing-can-supply",
                item.span.clone(),
                format!(
                    "'{question}' asks to show '{name}', and nothing where this question \
                     is put has a '{name}' to show — so that line is dropped in silence \
                     and the person is shown one value fewer than you wrote."
                ),
                format!("Change it to one of: {}.", allowed.join(", ")),
            ));
        }
    }

    // ── the park where NONE of them land ─────────────────────────────────────
    //
    // Per BINDING, which the rule above cannot be. `check_shows` used to exempt
    // a whole question the moment ANY binding of it was an action park, so the
    // worked example's `if-someone-fails: ask-a-person` put a decision to a
    // person with no facts at all: `is-this-ok` was bound both by a policy rule
    // (open) and by `teamwork.asks` (closed), and its
    // `shows: [amount, order-number]` was never held against the teammate park.
    // The screen rendered the wording and nothing else — not who failed, not
    // why, not who did answer.
    //
    // Only when the binding can supply NOTHING. A question shared between two
    // parks legitimately names values each can supply, and one that does not fit
    // where the run stopped is simply not shown; a screen with nothing on it is
    // a different thing, and it is the one a person cannot act on.
    //
    // One message per distinct VOCABULARY, not per line that puts the question.
    // `policies/approvals.yaml` says `applies-to: every-agent`, so its
    // `zendesk/reply` rule binds `is-this-ok` once per agent — and three copies
    // of one warning is three things to fix for one edit, which is the noise
    // `check_deadline` is deduplicated to avoid one function down.
    let mut said: std::collections::BTreeSet<&[String]> = Default::default();
    for binding in &asked.bindings {
        if binding.open || binding.names.is_empty() || !said.insert(&binding.names) {
            continue;
        }
        let lands = written.iter().any(|item| {
            item.as_str()
                .map(str::trim)
                .is_some_and(|n| binding.names.iter().any(|known| known == n))
        });
        if lands {
            continue;
        }
        let Some(first) = written.first() else {
            continue;
        };
        diags.push(Diagnostic::warning(
            "loader/shows-nothing-at-this-park",
            first.span.clone(),
            format!(
                "'{question}' is also put where none of the values it shows exist, so the \
                 person is asked to decide with the wording and nothing else in front of \
                 them."
            ),
            format!(
                "Give this question its own file with `shows: [{}]`, and point the line \
                 that puts it there at that one — or add those names here.",
                binding.names.join(", ")
            ),
        ));
    }
}

/// A timeout action nothing can ever reach.
///
/// The defect this whole module exists to make impossible: a line the author
/// wrote that nothing can ever read. `if-nobody-answers:` is `required: yes`, so
/// every question says what to do when the time runs out — but with no
/// `answer-within:` the time never runs out, and that instruction is dead text.
/// Reported where the author is, with the line to type.
///
/// Once per QUESTION rather than once per line that puts it. Three
/// `ask-a-person` rules naming `is-this-ok` are three waits a scheduler must
/// time separately — which is why the report lists three — but one file with one
/// missing line in it, and three copies of the same warning is three things to
/// fix for one edit.
///
/// The question is whether the line was WRITTEN, not whether it parsed. Gating
/// this on `milliseconds(..).is_some()` made every unreadable deadline into a
/// missing one, so `answer-within: "99999999999999999999h ..."` — already
/// refused by name, on its own line, one paragraph above — was then told it was
/// never written at all, which is false and unfixable. The schema owns "that is
/// not a length of time this can keep"; this owns "there is no line here". One
/// mistake, one message, is the same rule the once-per-question count below
/// keeps.
fn check_deadline(question: &str, q: &Node, asked: &Asked, diags: &mut Diagnostics) {
    let if_nobody_answers = q
        .get("if-nobody-answers")
        .and_then(Node::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if q.get("answer-within").is_some() || if_nobody_answers.is_empty() {
        return;
    }
    let span = key_span(q, "if-nobody-answers").unwrap_or_else(|| q.span.clone());
    let mut d = Diagnostic::warning(
        "loader/wait-with-no-deadline",
        span,
        format!(
            "'{question}' says what to do when nobody answers — {if_nobody_answers} — \
             but never says how long they have. The time never runs out, so that line \
             can never happen: the wait lasts until somebody answers."
        ),
        "Add a line beside it saying how long they have, like `answer-within: 30m`.",
    );
    if let Some(at) = &asked.first {
        d = d.with_related(at.clone(), "this is the line that starts the wait");
    }
    diags.push(d);
}

/// A wait answered by one of this workspace's own agents.
///
/// The whole of a human-in-the-loop gate is that a PERSON decides. `asked-of:`
/// is `list of text` with no `names:` — deliberately, because a register of
/// people would make the portable folder depend on one host's inventory — and
/// the cost of that freedom was that it accepted anything, including the name of
/// the agent it gates. MEASURED: `asked-of: [desk]` on the question that gates
/// `desk` printed "OK — loaded cleanly (51 settings)", and `pact waits` then
/// published `"asked-of": ["desk"], "escalates-to": ["desk"]` — a live approval
/// where the thing being checked does the checking, and escalates to itself when
/// nobody answers.
///
/// A NEGATIVE constraint, which is why it needs no register: saying who may not
/// answer costs nothing a portable folder cannot know. Both fields are held,
/// because escalation is where a gate ends up when the first person is away, and
/// a gate that escalates to the agent is a gate that opens itself on a timer.
fn check_nobody_approves_their_own_work(
    question: &str,
    q: &Node,
    document: &Node,
    diags: &mut Diagnostics,
) {
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        return;
    };
    for field in ["asked-of", "escalates-to"] {
        for name in strings(q.get(field)) {
            if !agents.contains_key(name.as_str()) {
                continue;
            }
            let span = key_span(q, field).unwrap_or_else(|| q.span.start_of_block());
            diags.push(Diagnostic::error(
                "loader/approves-its-own-work",
                span,
                format!(
                    "'{question}' {} '{name}', and '{name}' is one of this workspace's \
                     own agents — so the thing being checked is what does the checking.",
                    if field == "asked-of" {
                        "is asked of"
                    } else {
                        "escalates to"
                    }
                ),
                format!(
                    "Name the people who decide instead — an audience like \
                     `support-leads`. `{field}:` is who a person is, not which agent runs."
                ),
            ));
        }
    }
}

/// A wait nobody named can answer.
///
/// `asked-of:` is required by the schema, so an ABSENT line is caught there.
/// This is the other spelling of the same hole — `asked-of: []`, which is a
/// line the author wrote and which means, in the field's own words, *"nobody can
/// answer, not that anybody can"*. A run parks, the deadline runs down, and
/// `if-nobody-answers:` happens to somebody who was never asked.
fn check_somebody_can_answer(question: &str, q: &Node, asked: &Asked, diags: &mut Diagnostics) {
    if !strings(q.get("asked-of")).is_empty() {
        return;
    }
    // `start_of_block` and not the whole node — which is the precise defect that
    // method was written for. Falling back to `q.span` put eighty carets under
    // `description:`, the one line in the file that is correct.
    let span = key_span(q, "asked-of").unwrap_or_else(|| q.span.start_of_block());
    let mut d = Diagnostic::error(
        "loader/nobody-can-answer",
        span,
        format!(
            "'{question}' names nobody to ask, so the run stops, nobody hears about it, \
             and the deadline decides."
        ),
        "Write the team or the person who really decides, like \
         `asked-of: [support-leads]`."
            .to_string(),
    );
    if let Some(at) = &asked.first {
        d = d.with_related(at.clone(), "this is the line that starts the wait");
    }
    diags.push(d);
}

/// One wait, read off the question the author already wrote.
fn read_wait(
    reason: &'static str,
    agent: &str,
    question: &str,
    declared_at: Span,
    q: &Node,
) -> Wait {
    let answer_within = q
        .get("answer-within")
        .and_then(Node::as_str)
        .unwrap_or("")
        .trim();
    let deadline_ms = milliseconds(answer_within);
    let if_nobody_answers = q
        .get("if-nobody-answers")
        .and_then(Node::as_str)
        .unwrap_or("")
        .trim()
        .to_string();

    Wait {
        reason,
        agent: agent.to_string(),
        question: question.to_string(),
        declared_at,
        answer_within: answer_within.to_string(),
        deadline_ms,
        if_nobody_answers,
        asked_of: strings(q.get("asked-of")),
        escalates_to: strings(q.get("escalates-to")),
    }
}

// ─────────────────────────────────────────────────────────────────────── reading

/// Does `node`'s `field` say exactly `value`?
fn says(node: &Node, field: &str, value: &str) -> bool {
    node.get(field).and_then(Node::as_str).map(str::trim) == Some(value)
}

/// The name `field` holds, and the span of the line holding it.
fn named(node: &Node, field: &str) -> Option<(String, Span)> {
    let name = node.get(field).and_then(Node::as_str)?.trim().to_string();
    if name.is_empty() {
        return None;
    }
    Some((
        name,
        key_span(node, field).unwrap_or_else(|| node.span.clone()),
    ))
}

/// Which top-level map an agent's indirection field resolves against.
fn collection_for(field: &str) -> &'static str {
    match field {
        "policy" => "policies",
        "loop" => "loops",
        _ => "context-policies",
    }
}

/// The entry of `collection` that this agent's `field` names — the indirection
/// `policy: approvals` and `loop: careful` are both written as.
fn named_in<'a>(
    document: &'a Node,
    collection: &str,
    agent: &Node,
    field: &str,
) -> Option<&'a Node> {
    let key = agent.get(field).and_then(Node::as_str)?.trim();
    document.get(collection)?.get(key)
}

/// The span of a key, so a diagnostic underlines the setting rather than the
/// whole file.
fn key_span(node: &Node, field: &str) -> Option<Span> {
    node.as_map()
        .and_then(|m: &Map| m.get(field))
        .map(|e: &Entry| e.key_span.clone())
}

/// A `list of text` field, tolerant of the single-item spelling an author
/// reaches for (`asked-of: support-leads`).
fn strings(node: Option<&Node>) -> Vec<String> {
    match node {
        Some(n) => match n.as_str() {
            Some(one) => vec![one.trim().to_string()],
            None => n
                .as_list()
                .map(|l| {
                    l.iter()
                        .filter_map(Node::as_str)
                        .map(|s| s.trim().to_string())
                        .collect()
                })
                .unwrap_or_default(),
        },
        None => Vec::new(),
    }
}

/// `30m`, `4h`, `1m30s` — read through the schema's own duration reader.
///
/// Not a second implementation. `suspension.py` makes the same choice and says
/// why: the near-copies it replaced read `1m30s` as one second, a wait ninety
/// times shorter than the one written, with nothing anywhere to say so.
fn milliseconds(written: &str) -> Option<u64> {
    if written.is_empty() {
        return None;
    }
    // The reader takes a node because that is what a schema check has; the span
    // is never looked at on this path, so an empty one is honest about that.
    let node = Node::str(written, Span::whole_file(Utf8PathBuf::new()));
    match pact_schema::coerce::check(&node, &pact_schema::Ty::Duration) {
        Some(pact_schema::coerce::Coerced::Duration(ms)) => Some(ms),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn doc(text: &str) -> Node {
        parse_yaml(text, camino::Utf8Path::new("test.yaml")).expect("parses")
    }

    #[test]
    fn a_tree_with_no_agents_produces_no_waits() {
        let mut d = Diagnostics::new();
        let report = LoadReport::of(
            &doc("
questions:
  x:
    answer-within: 5m
"),
            &mut d,
        );
        assert!(report.waits.is_empty());
        assert!(d.is_empty(), "nothing to warn about when nothing can stop");
    }

    #[test]
    fn a_deadline_the_author_wrote_is_reported_in_milliseconds() {
        let mut d = Diagnostics::new();
        let report = LoadReport::of(
            &doc("
agents:
  desk:
    limits:
      when-it-runs-out: ask-a-person
      asks: keep-going
questions:
  keep-going:
    answer-within: 1m30s
    if-nobody-answers: stop-and-say-so
"),
            &mut d,
        );
        assert_eq!(report.waits.len(), 1);
        assert_eq!(report.waits[0].reason, OUT_OF_BUDGET);
        assert_eq!(report.waits[0].answer_within, "1m30s");
        assert_eq!(
            report.waits[0].deadline_ms,
            Some(90_000),
            "not ninety times shorter"
        );
    }

    #[test]
    fn a_timeout_action_with_no_deadline_is_reported_as_a_line_nothing_can_read() {
        let mut d = Diagnostics::new();
        let report = LoadReport::of(
            &doc("
agents:
  desk:
    limits:
      when-it-runs-out: ask-a-person
      asks: keep-going
questions:
  keep-going:
    if-nobody-answers: escalate
"),
            &mut d,
        );
        assert_eq!(
            report.waits.len(),
            1,
            "the wait is still real, it just never ends"
        );
        assert!(!report.waits[0].wakes());
        assert_eq!(
            report.wake_ups().count(),
            0,
            "a scheduler has no moment to wake at"
        );

        // AND THE PROJECTION SAYS SO. This is the only fixture in the tree with a
        // wait that never ends, so it is the only place the filter can be shown to
        // filter: every wait in the worked example carries a deadline, so a
        // `wake-ups` list that forgot to filter is indistinguishable there. Both
        // mutations — hardcoding `wakes: true`, and dropping the filter — pass
        // every example-based test and fail here.
        let json = report.to_json();
        assert_eq!(json["waits"][0]["wakes"], false, "{json:#}");
        assert!(
            json["wake-ups"].as_array().expect("a list").is_empty(),
            "a wait with no deadline must not be offered to a scheduler: {json:#}"
        );

        let warn = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/wait-with-no-deadline")
            .expect("a line nothing can read must be said out loud");
        assert!(warn.message.contains("keep-going"));
        assert!(
            warn.fix.contains("answer-within"),
            "the fix has to be typeable"
        );
        assert_eq!(
            warn.related.len(),
            1,
            "and it names the line that starts the wait"
        );
    }

    #[test]
    fn a_wait_with_neither_deadline_nor_timeout_action_is_left_alone() {
        // WAIT-8: waiting forever is what you get when you write nothing. The
        // warning above is about a line that contradicts itself, not about
        // silence.
        let mut d = Diagnostics::new();
        let report = LoadReport::of(
            &doc("
agents:
  desk:
    limits:
      when-it-runs-out: ask-a-person
      asks: keep-going
questions:
  keep-going:
    says: Keep going?
    asked-of: [support-leads]
"),
            &mut d,
        );
        assert_eq!(report.waits.len(), 1);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_question_naming_nobody_is_a_wait_nobody_can_answer_and_is_said_so() {
        // `asked-of:`'s own help says naming nobody means nobody can answer. The
        // run parks, the deadline runs down, and `if-nobody-answers:` happens to
        // somebody who was never asked.
        let mut d = Diagnostics::new();
        LoadReport::of(
            &doc("
agents:
  desk:
    limits:
      when-it-runs-out: ask-a-person
      asks: keep-going
questions:
  keep-going:
    says: Keep going?
    asked-of: []
"),
            &mut d,
        );
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/nobody-can-answer")
            .expect("a wait nobody can answer must be said out loud");
        assert!(
            e.fix.contains("asked-of: [support-leads]"),
            "the fix has to be typeable: {}",
            e.fix
        );
    }

    #[test]
    fn every_ask_a_person_rule_gets_its_own_entry_not_only_the_first() {
        // The harness keeps one rule per reason because a running wait has one
        // deadline. A scheduler told only about the first has no timer for the
        // second, which is a run that parks and is never looked at again.
        let mut d = Diagnostics::new();
        let report = LoadReport::of(
            &doc("
agents:
  desk:
    policy: approvals
policies:
  approvals:
    ask-a-person:
      - question: is-this-ok
      - question: how-much
questions:
  is-this-ok:
    answer-within: 30m
    if-nobody-answers: escalate
  how-much:
    answer-within: 4h
    if-nobody-answers: decline
"),
            &mut d,
        );
        let named: Vec<&str> = report.waits.iter().map(|w| w.question.as_str()).collect();
        assert_eq!(named, vec!["is-this-ok", "how-much"]);
        assert_eq!(report.waits[1].deadline_ms, Some(4 * 60 * 60 * 1000));
        assert_eq!(report.waits[1].if_nobody_answers, "decline");
    }

    #[test]
    fn a_name_with_no_question_behind_it_is_left_to_the_reference_check() {
        let mut d = Diagnostics::new();
        let report = LoadReport::of(
            &doc("
agents:
  desk:
    limits:
      when-it-runs-out: ask-a-person
      asks: is-this-okay
questions:
  is-this-ok:
    answer-within: 30m
"),
            &mut d,
        );
        assert!(report.waits.is_empty());
        assert!(d.is_empty(), "one mistake gets one message, from REF-1");
    }
}
