//! **An action that moves money, and no rule that asks anybody first.**
//!
//! `spends-money:` promises three things in its own help — a same-request key,
//! a durable record, and *"your approval policy: write a rule in `policies/`
//! naming this action, or nothing asks a person before the money moves"*. The
//! first is refused by the schema (`needed-when: {same-request-key: 'yes'}`).
//! The third was decided **only by running the agent**: `_money_moving` in
//! `adapters/python/src/pact_adapters/ir.py` walked `uses:` -> `tools.<t>.actions`
//! -> `policies.<p>.ask-a-person` and put a sentence on `RunResult.money_moving`,
//! which reached the author on a field of a result object, in another language,
//! in a process D13's reader never starts.
//!
//! Reproduced before this module: delete the two `payments/issue-refund` rules
//! from `examples/refund-desk/policies/approvals.yaml` and
//! `pact check examples/refund-desk` prints *"OK — … loaded cleanly (489
//! settings)"* and exits 0, while a Python run of the same tree reports
//! *"money moves without anybody being asked"*. Every fact in that sentence is
//! in the tree: which tool the agent `uses:`, which of its actions ticks
//! `spends-money:`, and which action each rule in that agent's policy names. It
//! is decidable at load time, so it is decided here — where the author is.
//!
//! # Why the schema cannot state it
//!
//! The same reason `approvals.rs` gives, one level further out. `needed-when:`
//! holds one field of one document against another field of the *same* document.
//! Whether an action is guarded is a fact about a **different** document — a
//! policy the agent points at through `policy:`, naming `<tool>/<action>`, two
//! names in one string. Nothing a field can say about itself reaches that.
//!
//! # A warning, not an error
//!
//! A workspace may genuinely intend an ungated spend — an internal ledger
//! transfer, a top-up under a figure nobody reviews, a tree mid-edit whose
//! policy is being written next. Refusing to load would make that unauthorable,
//! which is the wrong ceiling: PACT's job is to make sure nobody arrives at an
//! ungated spend *without having been told*, not to forbid one. `unnamed.rs`
//! makes the same call about an unattached policy, for the same reason.
//!
//! # What it deliberately stays quiet about
//!
//! One mistake gets one message.
//!
//! - An agent whose `policy:` names a policy this workspace has not got says
//!   nothing here: `names: policies` already reports it at the line the author
//!   typed, and *"no rule in its approval policy names this"* is a strange
//!   second thing to read when you have just misspelled the policy's name.
//! - A rule naming a bare tool (`tool: payments`) counts as guarding every
//!   action of it, exactly as `_money_moving` counted it. It is already an
//!   ERROR — `loader/rule-names-no-action`, *"whatever runs your agents cannot
//!   tell whether a call is the one you meant"* — so warning here as well would
//!   be two diagnostics about one edit, and the second would contradict the
//!   first about whether the rule guards anything.
//! - A tool no agent `uses:` moves no money, so it is not walked at all.
//! - An action carrying `needs-a-person: yes` is guarded, and says nothing here.
//!   That line is the one-line spelling of the very rule this warning tells the
//!   author to write (F17, `approvals::desugared`), so reporting it would be a
//!   warning that money moves unasked about the action whose own file says a
//!   person is asked — and a fix telling them to write out the long form of the
//!   line they already wrote. A field wired into the gate and left out of the
//!   check beside it is the same defect as a field nothing reads, one file over.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node};
use std::collections::{BTreeMap, BTreeSet};

/// Warn about every `spends-money: yes` action an agent can reach that no rule
/// in that agent's approval policy names.
///
/// Takes the loaded document and nothing else — the same purity `LoadReport::of`
/// keeps, and the reason this can run beside every other check in one pass.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    // Before anything about reachability: an action cannot say both of the two
    // things that decide whether it is dangerous. See
    // [`a_lookup_does_not_also_spend`] for why this walks every tool rather than
    // only the ones an agent can reach.
    a_lookup_does_not_also_spend(document, diags);
    money_that_moves_with_nobody_asked(document, diags);
    compared_in_the_shape_the_argument_has(document, diags);

    let Some(agents) = document.get("agents").and_then(Node::as_map) else { return };
    let Some(tools) = document.get("tools").and_then(Node::as_map) else { return };
    let policies = document.get("policies").and_then(Node::as_map);

    // Keyed by the action, not by the agent: a tool used by three agents that
    // none of them guard is ONE line to fix in ONE file, so it is one sentence
    // naming all three. Three copies of it at the same line of the same file
    // would be the pile-on `reachability.rs` collapses for the same reason.
    let mut ungated: BTreeMap<(String, String), Ungated> = BTreeMap::new();

    for (agent, entry) in agents {
        let Some(guarded) = guarded_by(&entry.node, policies) else { continue };
        for tool in uses(&entry.node) {
            let Some(found) = tools.get(tool) else { continue };
            let Some(actions) = found.node.get("actions").and_then(Node::as_map) else { continue };
            for (action, spec) in actions {
                same_request_key_is_an_argument(tool, action, &spec.node, diags);
                let Some((span, written)) = moves_money(&spec.node) else { continue };
                // `needs-a-person: yes` IS a rule naming this action — see the
                // module note. It is asked here rather than folded into
                // `guarded_by` because it is a fact about the ACTION and not
                // about the agent's policy, and putting it in that set would
                // make `guarded` mean two different things.
                if guarded.contains(&format!("{tool}/{action}"))
                    || guarded.contains(tool)
                    || crate::approvals::asked_for(&spec.node)
                {
                    continue;
                }
                ungated
                    .entry((tool.to_string(), action.clone()))
                    .or_insert_with(|| Ungated { span, written, who: BTreeSet::new() })
                    .who
                    .insert(agent.clone());
            }
        }
    }

    for ((tool, action), found) in ungated {
        let who = and_list(&found.who);
        // "its approval policy" for one agent, "their approval policies" for
        // several. The article/agreement bar `diagnostics_read_as_english.rs`
        // sets is about the first sentence a D13 reader ever gets from the tool;
        // "no rule in their approval policy" fails it just as "a agent" does.
        let (whose, book) = if found.who.len() == 1 {
            ("its", "approval policy")
        } else {
            ("their", "approval policies")
        };
        diags.push(Diagnostic::warning(
            "loader/money-moves-with-nobody-asked",
            found.span,
            // The wording `_money_moving` produced, kept word for word from
            // "can call it" onward so the sentence an author meets did not
            // change when the check moved languages. One tense change: it said
            // *"was not applied"*, which is true of a run that has finished and
            // is a claim about the past that `pact check` cannot make — nothing
            // has run yet, and that is the whole point of moving it here.
            format!(
                "`spends-money: {}` on `{action}` is not applied: {who} can call it and \
                 no rule in {whose} {book} names `{tool}/{action}`, so money moves without \
                 anybody being asked.",
                // The word the author typed, not the word this file would have
                // chosen. `authoring_surface.rs` holds the loop diagnostics to
                // exactly this — *"the word a diagnostic uses for a stage is the
                // word the author typed"* — and quoting `yes` back at somebody
                // who wrote `enabled` sends them looking for a line they have not
                // got.
                found.written
            ),
            // Two fixes, shortest first, because they are not the same size.
            // `needs-a-person: yes` is one line in the file already open and it
            // is the whole gate (F17); the rule below it is three files and
            // thirteen lines, and is what you write when the decision belongs to
            // a named team, or only above a figure, or needs an answer a yes
            // cannot carry. Offering only the second was measured to cost a
            // first-time author four rounds of diagnostics before their first
            // gate held.
            format!(
                "Write `needs-a-person: yes` under `{action}` in `tools/{tool}.yaml`, and \
                 whoever runs {who} is asked before every call to it. Add a rule to \
                 `policies/` instead — `- when: [{{ tool: {tool}/{action} }}]`, with a \
                 `because:` and a `question:` — when the decision belongs to a named team, \
                 or only above a figure, and point the `policy:` line of {who} at that \
                 file."
            ),
        ));
    }
}

/// **`reads-only:` — the sibling of `needs-a-person:` that nothing read.**
///
/// Wiring one field on the `action` block and leaving the field beside it idle
/// is this project's recurring defect, so when `needs-a-person:` was wired (F17)
/// its neighbours were counted. Seven of the eight are read somewhere;
/// `reads-only:` was read by NOTHING — not the loader, not an adapter, not the
/// second port. It is written twice in the shipped worked example
/// (`tools/payments.yaml`, `tools/zendesk.yaml`) and once in
/// `tests/trees/one-line-gate/`, and every one of those lines was decoration.
///
/// It is now the one line that CONTRADICTS the other: `reads-only: yes` says
/// this action only looks things up, `spends-money: yes` says it moves money,
/// and both cannot be true of one action. That matters because the two lines
/// pull the rest of the file in opposite directions — `spends-money:` is what
/// forces a same-request key and what makes
/// `loader/money-moves-with-nobody-asked` fire, while `reads-only:` is the
/// author's own statement that nobody needs to be asked. Whichever a reader
/// believes decides whether a person stands in front of the money, and picking
/// one silently is the governance setting that quietly changed that T7 forbids.
///
/// **An error, not a warning**, and the one place this file differs from the
/// check below it. That one is about a policy that has not been written yet, and
/// a workspace may genuinely mean an ungated spend. This is about a single
/// action saying two opposite things about itself in two adjacent lines: there
/// is no tree in which both are what the author meant, so there is nothing to
/// leave open.
///
/// **Walked over every tool, not only the reachable ones.** The warning below
/// asks *"can an agent get to this money?"*, which is a fact about `uses:`. This
/// asks *"does this action describe itself twice, differently?"*, which is a
/// fact about the eight lines in front of the author — and a tool nobody uses
/// yet is exactly the tool being written right now.
///
/// `reads-only: yes` beside `needs-a-person: yes` is deliberately fine: reading
/// a customer's card details may very well need somebody's say-so, and refusing
/// that would make a legitimate gate unwritable.
/// An action that takes an amount of money and does not say it moves any (B12).
///
/// `spends-money:` is the switch, and its own help promises three things: a
/// same-request key so the same payment cannot go twice, an approval rule so
/// somebody is asked, and the cross-agent walk above. MEASURED: an action with
/// `takes: {amount: money}`, `inspects: [amount]` and no `spends-money:` line
/// printed *"OK — loaded cleanly (51 settings)"* with zero diagnostics — so all
/// three were off, and the one word that turns them on was the one word nobody
/// was prompted for.
///
/// The type is the evidence. An author who declared an argument as an amount of
/// money has already said what the action does with it; asking them to say it
/// again under a different name is the second spelling this project refuses
/// everywhere else, and NOT asking them is three guarantees quietly absent.
///
/// A WARNING, for the same reason `unnamed.rs` gives: an action may genuinely
/// take a figure it only reports on — a quote, an estimate, a balance — and
/// `spends-money: no` is the line that says so. What must never happen is
/// silence, because the silent case and the correct case look identical.
fn money_that_moves_with_nobody_asked(document: &Node, diags: &mut Diagnostics) {
    let Some(tools) = document.get("tools").and_then(Node::as_map) else { return };
    for (tool, entry) in tools {
        let Some(actions) = entry.node.get("actions").and_then(Node::as_map) else { continue };
        for (action, spec) in actions {
            if spec.node.get("spends-money").is_some() {
                continue;
            }
            let Some(takes) = spec.node.get("takes").and_then(Node::as_map) else { continue };
            let Some((argument, at)) = takes
                .iter()
                .find(|(_, v)| v.node.as_str().map(str::trim) == Some("money"))
                .map(|(k, v)| (k.clone(), v.key_span.clone().merge(&v.node.span)))
            else {
                continue;
            };
            diags.push(Diagnostic::warning(
                "loader/money-that-moves-with-nobody-asked",
                at,
                format!(
                    "`{action}` on `{tool}` takes `{argument}`, which is an amount of \
                     money, and does not say `spends-money:`. So none of the three things \
                     that guard money is on: no same-request key, no approval rule, no \
                     cross-agent check."
                ),
                format!(
                    "Add `spends-money: yes` next to `takes:` in the `{action}` block — or \
                     `spends-money: no` if this action only reads a figure and moves nothing."
                ),
            ));
        }
    }
}

/// A gate that compares an argument in a shape the argument does not have (A3).
///
/// `more-than:` used to be `type: money`, which was right while money was the
/// only thing a gate could compare. MEASURED, before this: a lead score gated
/// with `more-than: 80` was told *"'more-than' should be an amount of money …
/// fix: Write it like `0.05 USD`"* — and doing exactly what that said printed
/// "OK — loaded cleanly", after which `pact waits` showed a live thirty-minute
/// human gate comparing a score to dollars.
///
/// The shape cannot be stated in the schema, because it is the shape of an
/// argument declared in a DIFFERENT document — the tool's `takes:`. This is the
/// only place that reads both, which is why the check is here and the schema is
/// permissive rather than the other way round.
fn compared_in_the_shape_the_argument_has(document: &Node, diags: &mut Diagnostics) {
    let Some(policies) = document.get("policies").and_then(Node::as_map) else { return };
    let Some(tools) = document.get("tools").and_then(Node::as_map) else { return };

    for (_, policy) in policies {
        let Some(rules) = policy.node.get("ask-a-person").and_then(Node::as_list) else { continue };
        for rule in rules {
            let Some(whens) = rule.get("when").and_then(Node::as_list) else { continue };
            for when in whens {
                let Some(named) = when.get("tool").and_then(Node::as_str) else { continue };
                let Some(argument) = when.get("arg").and_then(Node::as_str) else { continue };
                let Some((tool, action)) = named.split_once('/') else { continue };
                let Some(declared) = tools
                    .get(tool)
                    .and_then(|t| t.node.get("actions"))
                    .and_then(|a| a.get(action))
                    .and_then(|a| a.get("takes"))
                    .and_then(|t| t.get(argument.trim()))
                    .and_then(Node::as_str)
                    .map(str::trim)
                else {
                    continue;
                };
                // Only `more-than:` compares a magnitude; `is:` and `is-one-of:`
                // compare a value, and any shape can be equal to something.
                let Some(figure) = when.get("more-than") else { continue };
                // A bare `200` parses as an integer, and that is exactly the
                // half of the mismatch worth catching: a money argument gated by
                // a number with no currency. Reading only strings would have
                // caught the score-gated-by-dollars direction and silently
                // missed its mirror.
                let written = match &figure.value {
                    pact_doc::Value::Str(s) => s.trim().to_string(),
                    pact_doc::Value::Int(n) => n.to_string(),
                    pact_doc::Value::Float(n) => n.to_string(),
                    _ => continue,
                };
                let written = written.as_str();
                let looks_like_money = written
                    .split_whitespace()
                    .last()
                    .is_some_and(|w| w.len() == 3 && w.chars().all(|c| c.is_ascii_alphabetic()))
                    || written.starts_with('$');
                let is_money = declared == "money";
                if is_money == looks_like_money {
                    continue;
                }
                let (says, fix) = if is_money {
                    (
                        format!(
                            "`{argument}` is an amount of money and `more-than: {written}` \
                             is not"
                        ),
                        format!("Write the figure the way the argument is declared, like `{written} USD`."),
                    )
                } else {
                    (
                        format!(
                            "`{argument}` is {declared} and `more-than: {written}` is an \
                             amount of money"
                        ),
                        "Write the figure the way the argument is declared — a bare number \
                         for a number, with no currency after it."
                            .to_string(),
                    )
                };
                diags.push(Diagnostic::error(
                    "loader/compared-in-the-wrong-shape",
                    figure.span.clone(),
                    format!(
                        "this rule asks a person when `{named}` is called, and {says} — so \
                         the gate compares two different kinds of thing."
                    ),
                    fix,
                ));
            }
        }
    }
}

fn a_lookup_does_not_also_spend(document: &Node, diags: &mut Diagnostics) {
    let Some(tools) = document.get("tools").and_then(Node::as_map) else { return };
    for (tool, entry) in tools {
        let Some(actions) = entry.node.get("actions").and_then(Node::as_map) else { continue };
        for (action, spec) in actions {
            let Some((looks_up, said)) = only_looks_things_up(&spec.node) else { continue };
            let Some((spends, ticked)) = moves_money(&spec.node) else { continue };
            diags.push(
                Diagnostic::error(
                    "loader/looks-things-up-and-spends",
                    looks_up,
                    format!(
                        "`{action}` on `{tool}` says `reads-only: {said}`, which means it \
                         only looks things up, and `spends-money: {ticked}`, which means it \
                         moves money. Both cannot be true of one action, and which one is \
                         believed decides whether anybody is asked before the money goes."
                    ),
                    format!(
                        "Delete `reads-only: {said}` from the `{action}` block if it really \
                         does move money — then write `needs-a-person: yes` under it so \
                         somebody is asked. Delete `spends-money: {ticked}` instead if it \
                         only looks things up."
                    ),
                )
                .with_related(spends, "the line that says it moves money"),
            );
        }
    }
}

/// Where `reads-only:` is on an action that ticks it, and how the tick was
/// spelled. `None` when the action says nothing about only looking things up.
///
/// Read through the schema's own yes/no reader for the reason [`moves_money`]
/// gives at length: `yes`, `y`, `true`, `on` and `enabled` are all a yes to the
/// validator, so a tick this did not recognise would be a contradiction that
/// loads clean.
fn only_looks_things_up(action: &Node) -> Option<(Span, String)> {
    let entry = action.as_map()?.get("reads-only")?;
    match pact_schema::coerce::check(&entry.node, &pact_schema::Ty::YesNo) {
        Some(pact_schema::coerce::Coerced::YesNo(true)) => {
            // Key and value together, because the message quotes the whole
            // setting — the same underline `moves_money` builds, for the same
            // reason.
            let span = entry.key_span.clone().merge(&entry.node.span);
            let written = match &entry.node.value {
                pact_doc::Value::Str(s) => s.trim().to_string(),
                _ => "true".to_string(),
            };
            Some((span, written))
        }
        _ => None,
    }
}

/// The argument `same-request-key:` names has to be one the action takes.
///
/// The field the schema FORCES onto every money-moving action, and its value was
/// resolved by nothing: `same-request-key: ordr-number` printed *"OK — loaded
/// cleanly"* and exited 0, while the sibling field one line up (`bind:`) gave
/// `loader/no-such-run-input` with a fix for the same typo. So `spends-money:
/// yes` demanded a key, and a key naming nothing is the same refund paid twice,
/// printed as clean.
///
/// Held against `takes:` PLUS `bind:`, because a bound argument is a real
/// argument of the call — it is simply one the model did not choose.
///
/// Whether at-most-once is ENFORCED is a separate, runtime question. This is the
/// half that is decidable where the author is.
fn same_request_key_is_an_argument(
    tool: &str,
    action: &str,
    spec: &Node,
    diags: &mut Diagnostics,
) {
    let Some(entry) = spec.as_map().and_then(|m| m.get("same-request-key")) else { return };
    let Some(key) = entry.node.as_str().map(str::trim) else { return };
    if key.is_empty() {
        return;
    }
    let mut known: BTreeSet<&str> = BTreeSet::new();
    for field in ["takes", "bind"] {
        if let Some(args) = spec.get(field).and_then(Node::as_map) {
            known.extend(args.keys().map(String::as_str));
        }
    }
    if known.contains(key) {
        return;
    }
    let offer: Vec<&str> = known.into_iter().collect();
    diags.push(Diagnostic::error(
        "loader/no-such-request-key",
        entry.node.span.clone(),
        format!(
            "`same-request-key: {key}` on `{tool}/{action}` names an argument that \
             action does not take, so nothing can tell two calls apart and the same \
             payment could be made twice."
        ),
        if offer.is_empty() {
            format!(
                "Give `{action}` a `takes:` block first, then name one of its \
                 arguments here."
            )
        } else {
            format!("Change it to one of: {}.", offer.join(", "))
        },
    ));
}

/// One action nothing asks about: where its `spends-money:` line is, how the
/// author spelled the tick, and which agents can reach it.
struct Ungated {
    span: Span,
    written: String,
    who: BTreeSet<String>,
}

/// Every `<tool>` and `<tool>/<action>` this agent's approval policy names.
///
/// `None` means *say nothing about this agent*: its `policy:` line points at a
/// policy this workspace has not got, which `names: policies` reports where the
/// author typed it. An agent with **no** `policy:` line at all is a different
/// answer and a real one — an empty set, because nothing guards anything.
fn guarded_by(agent: &Node, policies: Option<&Map>) -> Option<BTreeSet<String>> {
    let mut guarded = BTreeSet::new();
    let named = agent.get("policy").and_then(Node::as_str).map(str::trim).unwrap_or("");
    let Some(all) = policies else {
        return Some(guarded);
    };
    if !named.is_empty() && all.get(named).is_none() {
        // The `policy:` line points at nothing. `names: policies` reports that
        // where the author typed it; saying anything about money here as well
        // would be a second message about one mistake.
        return None;
    }
    for (key, entry) in all {
        if !covers(&entry.node, key, named) {
            continue;
        }
        let Some(rules) = entry.node.get("ask-a-person").and_then(Node::as_list) else {
            continue;
        };
        for rule in rules {
            let Some(whens) = rule.get("when").and_then(Node::as_list) else { continue };
            for when in whens {
                if let Some(tool) = when.get("tool").and_then(Node::as_str) {
                    guarded.insert(tool.trim().to_string());
                }
            }
        }
    }
    Some(guarded)
}

/// Whether one policy covers one agent.
///
/// Two ways, and the second was missing everywhere: the policy the agent NAMES,
/// and any policy saying `applies-to: every-agent`. Approval was bound per-agent
/// and opt-in, which is the polarity `interceptor.applies-to` exists to correct
/// — and here the surface is money, not a leaked card number.
pub(crate) fn covers(policy: &Node, key: &str, named_by_the_agent: &str) -> bool {
    if key == named_by_the_agent {
        return true;
    }
    policy.get("applies-to").and_then(Node::as_str).map(str::trim) == Some("every-agent")
}

/// The tools and skills an agent's `uses:` line lists.
///
/// A single name written without a dash is the same line with one entry, so
/// both spellings are read — refusing the short one would be a rule about
/// punctuation rather than about money.
fn uses(agent: &Node) -> Vec<&str> {
    match agent.get("uses") {
        Some(n) if n.as_str().is_some() => vec![n.as_str().unwrap_or("").trim()],
        Some(n) => n
            .as_list()
            .map(|items| items.iter().filter_map(Node::as_str).map(str::trim).collect())
            .unwrap_or_default(),
        None => Vec::new(),
    }
}

/// Where `spends-money:` is on an action that ticks it, and how the tick was
/// spelled. `None` when the action does not move money.
///
/// Read through the schema's own yes/no reader rather than a second list of
/// spellings here, the way `report.rs` reads a duration and `teamwork.rs` a
/// percentage. `yes`, `y`, `true`, `on` and `enabled` are all a yes to the
/// validator, so all five have to be a yes to this too — a tick the checker
/// does not recognise is an ungated spend it reports as fine.
fn moves_money(action: &Node) -> Option<(Span, String)> {
    let entry = action.as_map()?.get("spends-money")?;
    match pact_schema::coerce::check(&entry.node, &pact_schema::Ty::YesNo) {
        Some(pact_schema::coerce::Coerced::YesNo(true)) => {
            // The whole setting is underlined, key and value, because the
            // message quotes the whole setting: an underline under `yes` alone
            // would name the word rather than the line.
            let span = entry.key_span.clone().merge(&entry.node.span);
            // The word the author typed, so the sentence quotes their line and
            // not a spelling this file preferred — `authoring_surface.rs` holds
            // the loop diagnostics to exactly that, and quoting `yes` back at
            // somebody who wrote `enabled` sends them looking for a line they
            // have not got. `yes`, `y`, `on` and `enabled` reach here as their
            // own text with their own capitalisation; only `true` is a value the
            // YAML core schema resolves, so `TRUE` arrives as a yes/no and is
            // named `true`. That is the one spelling this cannot give back
            // exactly, and it is still a word on the line being pointed at.
            //
            // NOT recovered by slicing the file at the span, which is the
            // obvious other way and is wrong: `Span::byte_start` is built from
            // yaml-rust2's `Marker::index()`, which counts CHARACTERS. The three
            // em-dashes in the worked example's own `tools/payments.yaml` put
            // that six bytes out, and the slice came back `one` — the middle of
            // the word `money` in the key above it.
            let written = match &entry.node.value {
                pact_doc::Value::Str(s) => s.trim().to_string(),
                _ => "true".to_string(),
            };
            Some((span, written))
        }
        _ => None,
    }
}

/// `a`, `a and b`, `a, b and c` — a list the way a sentence carries one.
///
/// Named quoted, because everywhere else in this diagnostic a name is in
/// backticks and a reader should not have to tell two conventions apart in one
/// sentence.
fn and_list(names: &BTreeSet<String>) -> String {
    let quoted: Vec<String> = names.iter().map(|n| format!("`{n}`")).collect();
    match quoted.split_last() {
        None => String::new(),
        Some((last, [])) => last.clone(),
        Some((last, rest)) => format!("{} and {last}", rest.join(", ")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    /// A workspace of the same shape as the worked example: one agent, one tool
    /// with a read-only action and a money-moving one, one policy naming it.
    const WORKSPACE: &str = "
agents:
  refund-desk:
    description: Decides refunds.
    uses: [payments]
    policy: approvals
tools:
  payments:
    description: Where refunds are issued.
    actions:
      look-up-order:
        description: Find an order.
        reads-only: yes
      issue-refund:
        description: Send money back.
        takes:
          amount: money
          order-number: text
        spends-money: yes
        same-request-key: order-number
policies:
  approvals:
    ask-a-person:
      - when:
          - { tool: payments/issue-refund, arg: amount, more-than: 200 USD }
        because: a refund over 200 USD is a management decision
        question: is-this-ok
";

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("workspace.yaml", text);
        check(&node, &mut d);
        d
    }

    fn only(d: &Diagnostics) -> &Diagnostic {
        assert_eq!(d.items().len(), 1, "expected exactly one warning:\n{}", d.render());
        &d.items()[0]
    }

    #[test]
    fn an_action_that_moves_money_and_is_named_by_a_rule_is_left_alone() {
        // The half that matters most: a correct tree must not be warned about.
        // A false positive on the shipped shape costs an author their trust in
        // every other line the tool prints.
        let d = check_text(WORKSPACE);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn an_action_that_moves_money_with_no_rule_naming_it_is_warned_about() {
        let d = check_text(&WORKSPACE.replace("tool: payments/issue-refund", "tool: zendesk/reply"));
        let e = only(&d);
        assert_eq!(e.rule, "loader/money-moves-with-nobody-asked");
        assert_eq!(e.severity, pact_diag::Severity::Warning, "an ungated spend may be intended");
        assert!(e.message.contains("money moves without anybody being asked"), "{}", e.message);
        assert!(e.fix.contains("`- when: [{ tool: payments/issue-refund }]`"), "{}", e.fix);
    }

    #[test]
    fn an_agent_with_no_approval_policy_at_all_is_the_case_this_exists_for() {
        let d = check_text(&WORKSPACE.replace("    policy: approvals\n", ""));
        assert!(
            only(&d).message.contains("no rule in its approval policy"),
            "{}",
            only(&d).message
        );
    }

    #[test]
    fn a_read_only_action_of_the_same_tool_is_never_mentioned() {
        // `spends-money:` is the trigger, not "is an action of a tool that has
        // one". Warning about `look-up-order` would teach an author to write
        // rules that gate reads.
        let d = check_text(&WORKSPACE.replace("    policy: approvals\n", ""));
        assert!(!only(&d).message.contains("look-up-order"), "{}", only(&d).message);
    }

    #[test]
    fn a_money_moving_tool_no_agent_uses_moves_no_money() {
        let d = check_text(&WORKSPACE.replace("    uses: [payments]\n", ""));
        assert!(d.is_empty(), "an unused tool is never called: {}", d.render());
    }

    #[test]
    fn a_policy_the_workspace_has_not_got_is_reported_once_and_not_twice() {
        // `names: policies` refuses the misspelling at the line the author
        // typed. A second sentence here would be a second thing to fix for one
        // edit, and it would be about the wrong file.
        let d = check_text(&WORKSPACE.replace("policy: approvals", "policy: aprovals"));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_rule_naming_the_whole_tool_counts_as_guarding_every_action_of_it() {
        // Deliberately quiet: `loader/rule-names-no-action` is already an ERROR
        // about that rule, so this document does not load either way, and two
        // diagnostics disagreeing about whether it guards anything is worse than
        // one.
        let d = check_text(&WORKSPACE.replace("tool: payments/issue-refund", "tool: payments"));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn every_spelling_of_yes_the_validator_accepts_is_a_spelling_of_yes_here() {
        // A tick the checker does not recognise is an ungated spend it reports
        // as fine, which is worse than not checking at all. And the sentence
        // quotes the word the author typed — `authoring_surface.rs` holds the
        // loop diagnostics to the same rule — so somebody who wrote `enabled` is
        // not sent looking for a `yes` they have not got.
        // `true`, `True` and `TRUE` are one value to the YAML core schema, so
        // the capitalisation is gone before this crate sees it and all three are
        // named `true` — the one spelling that cannot be given back exactly, and
        // still a word on the line being pointed at.
        for (tick, quoted) in [
            ("yes", "yes"),
            ("y", "y"),
            ("on", "on"),
            ("enabled", "enabled"),
            ("Yes", "Yes"),
            ("true", "true"),
            ("TRUE", "true"),
        ] {
            let text = WORKSPACE
                .replace("spends-money: yes", &format!("spends-money: {tick}"))
                .replace("tool: payments/issue-refund", "tool: zendesk/reply");
            let said = check_text(&text);
            assert_eq!(said.items().len(), 1, "'{tick}' was read as a no");
            assert!(
                said.items()[0].message.contains(&format!("`spends-money: {quoted}`")),
                "the sentence must quote what was typed: {}",
                said.items()[0].message
            );
        }
        for tick in ["no", "off", "disabled"] {
            let text = WORKSPACE
                .replace("spends-money: yes", &format!("spends-money: {tick}"))
                .replace("tool: payments/issue-refund", "tool: zendesk/reply");
            assert!(check_text(&text).is_empty(), "'{tick}' was read as a yes");
        }
    }

    #[test]
    fn several_agents_reaching_one_ungated_action_are_one_sentence_not_three() {
        let text = WORKSPACE.replace("tool: payments/issue-refund", "tool: zendesk/reply").replace(
            "tools:\n",
            "  night-desk:\n    description: Out of hours.\n    uses: [payments]\n\
             tools:\n",
        );
        let said = check_text(&text);
        let e = only(&said);
        assert!(e.message.contains("`night-desk` and `refund-desk`"), "{}", e.message);
        assert!(e.message.contains("in their approval policies"), "plural agrees: {}", e.message);
    }

    #[test]
    fn the_underline_covers_the_setting_the_sentence_quotes() {
        let d = check_text(&WORKSPACE.replace("tool: payments/issue-refund", "tool: zendesk/reply"));
        let rendered = d.render();
        assert!(rendered.contains("        spends-money: yes"), "the line is shown:\n{rendered}");
        assert!(
            rendered.contains(&"^".repeat("spends-money: yes".len())),
            "the whole setting is underlined, not just the word 'yes':\n{rendered}"
        );
    }

    #[test]
    fn a_workspace_with_no_tools_is_not_walked_at_all() {
        assert!(check_text("agents:\n  desk:\n    description: x\n").is_empty());
    }
}
