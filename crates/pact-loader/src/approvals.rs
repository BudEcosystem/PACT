//! **The tool an approval rule guards, held against the tools that exist.**
//!
//! `policies/approvals.yaml` is where money is gated, and for a round the name
//! inside each rule was checked by nothing at all. Reproduced on the shipped
//! example: change `payments/issue-refund` to `paymnets/issue-refund` in both
//! rules and `pact check` prints *"OK — … loaded cleanly"* and exits 0. Running
//! the same document through the harness with a 300 USD refund gives
//! `halted: final`, `parked: None`, and a tool result reading `paid 300 USD` —
//! with nothing on `RunResult.unenforced` to say the gate had gone. The control,
//! spelled correctly, parks with `needs-approval`.
//!
//! # Why the schema cannot do this on its own
//!
//! `names:` resolves a value against the keys of a map. The name here is not a
//! key of `tools:` — it is `<tool>/<action>`, two names in one string, and the
//! second half lives one level down under that tool's `actions:`. A plain
//! `names: tools` would refuse every correct rule in the worked example. So the
//! split happens here, and both halves are resolved: the head against `tools:`,
//! the tail against that tool's own `actions:`.
//!
//! # The other half: a rule that resolves and still gates nothing
//!
//! A rule naming one action used to be enforced by nobody: `Gate.unenforced` on
//! the executing side reported *"the rule about `zendesk/reply` was not
//! applied"* on every run, because the harness believed a call carried only a
//! tool name. It carries the action too — `ir._takes` declares `action:` on
//! every tool with an `actions:` block — so `zendesk/reply` now stops a reply
//! and lets `read-ticket` through, and only a call that names NO action is still
//! reported.
//!
//! That report goes to a `RunResult` field, and D13's reader runs `pact check`
//! and nothing else. [`arguments_exist`] is the check-time half: a rule that
//! looks at an argument the action does not declare, or that is not on its
//! `inspects:` list, is refused where the author is.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Entry, Map, Node};

/// Refuse an approval rule whose `tool:` names nothing, and a `bind:` that fills
/// an argument from a run input nobody declared.
///
/// Takes the loaded document and nothing else — the same purity `LoadReport::of`
/// keeps.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    bindings_resolve(document, diags);
    shorthand_and_rule_do_not_both_decide(document, diags);
    let Some(policies) = document.get("policies").and_then(Node::as_map) else {
        return;
    };
    let tools = document.get("tools").and_then(Node::as_map);
    for (_, policy) in policies {
        let Some(rules) = policy.node.get("ask-a-person").and_then(Node::as_list) else {
            continue;
        };
        for rule in rules {
            let Some(whens) = rule.get("when").and_then(Node::as_list) else { continue };
            for when in whens {
                one(when, tools, diags);
            }
        }
    }
}

/// `bind:` — the field whose help says it is *"how 'whose order' stops being
/// something the model decides"* — validated at all.
///
/// It was read by nothing and checked by nothing: `bind: { customer-id:
/// run-inputs.custommer-id }` loaded clean, and so did
/// `bind: { customer-id: whatever.i.like }`, a namespace that does not exist. So
/// the mechanism that keeps a customer id out of the model's hands was a comment.
///
/// Two rules, both about shape rather than about behaviour, because behaviour is
/// the host's: the value must be `run-inputs.<name>`, which is the only form the
/// tree can carry, and `<name>` must be one of the `run-inputs:` of an agent that
/// uses this tool.
fn bindings_resolve(document: &Node, diags: &mut Diagnostics) {
    let Some(tools) = document.get("tools").and_then(Node::as_map) else { return };
    // Every run input any agent supplies, with the agent it came from. A tool
    // may be used by several agents, and a binding is legitimate if ANY of them
    // supplies the name — narrowing it per agent would refuse a shared tool.
    let mut inputs: std::collections::BTreeSet<String> = Default::default();
    if let Some(agents) = document.get("agents").and_then(Node::as_map) {
        for (_, agent) in agents {
            if let Some(m) = agent.node.get("run-inputs").and_then(Node::as_map) {
                inputs.extend(m.keys().cloned());
            }
        }
    }
    for (tool, entry) in tools {
        let Some(actions) = entry.node.get("actions").and_then(Node::as_map) else { continue };
        for (action, a) in actions {
            let Some(bind) = a.node.get("bind").and_then(Node::as_map) else { continue };
            for (arg, value) in bind {
                let Some(written) = value.node.as_str().map(str::trim) else { continue };
                let Some(name) = written.strip_prefix("run-inputs.") else {
                    diags.push(Diagnostic::error(
                        "loader/not-a-binding",
                        value.node.span.clone(),
                        format!(
                            "`{arg}:` is filled in from '{written}', and the only thing a \
                             binding can be filled in from is one of the agent's own \
                             `run-inputs:`."
                        ),
                        offer(
                            "bind",
                            written,
                            &inputs.iter().map(String::as_str).collect::<Vec<_>>(),
                            "add it under `run-inputs:` in the agent that uses this tool",
                        )
                        .replace("Change the `bind:` to one of: ", "Write `run-inputs.<name>`, naming one of: "),
                    ));
                    continue;
                };
                if inputs.is_empty() || inputs.contains(name) {
                    continue;
                }
                diags.push(Diagnostic::error(
                    "loader/no-such-run-input",
                    value.node.span.clone(),
                    format!(
                        "`{tool}/{action}` fills `{arg}:` from a run input called \
                         '{name}', and no agent here supplies one by that name — so the \
                         model would choose that value after all, which is the one thing \
                         `bind:` exists to stop."
                    ),
                    format!(
                        "Change it to one of: {} — or add `{name}: text` under \
                         `run-inputs:` in the agent that uses this tool.",
                        inputs.iter().cloned().collect::<Vec<_>>().join(", ")
                    ),
                ));
            }
        }
    }
}

fn one(when: &Node, tools: Option<&Map>, diags: &mut Diagnostics) {
    let Some(entry) = when.as_map().and_then(|m| m.get("tool")) else { return };
    let Some(written) = entry.node.as_str().map(str::trim) else { return };
    if written.is_empty() {
        return;
    }
    let (tool, action) = match written.split_once('/') {
        Some((t, a)) => (t.trim(), a.trim()),
        // A bare tool name gates every action of it, which is a thing to want —
        // but it is not the spelling the field's help teaches, and the way to
        // want it here is a rule per action, which says out loud that the
        // read-only ones are being stopped as well.
        None => (written, ""),
    };

    let known: Vec<&str> = tools.map(|m| m.keys().map(String::as_str).collect()).unwrap_or_default();
    let Some(found) = tools.and_then(|m| m.get(tool)) else {
        diags.push(Diagnostic::error(
            "loader/no-such-tool-to-guard",
            entry.node.span.clone(),
            format!(
                "This rule guards '{tool}', and this workspace has no tool by that name — \
                 so the rule gates nothing and the call it was written about goes straight \
                 through."
            ),
            offer("tool", tool, &known, "add a file `tools/{}.yaml`"),
        ));
        return;
    };

    let actions = found.node.get("actions").and_then(Node::as_map);
    let names: Vec<&str> = actions.map(|m| m.keys().map(String::as_str).collect()).unwrap_or_default();
    if action.is_empty() {
        diags.push(Diagnostic::error(
            "loader/rule-names-no-action",
            entry.node.span.clone(),
            format!(
                "This rule guards '{tool}' and does not say which of its actions, so it \
                 would stop the read-only ones you wrote no rule about along with the one \
                 you meant."
            ),
            match names.first() {
                Some(first) => format!(
                    "Write `tool: {tool}/{first}`. The actions are: {}. To ask about every \
                     call to `{tool}`, write one rule for each of them.",
                    names.join(", ")
                ),
                None => format!(
                    "Give `tools/{tool}.yaml` an `actions:` block naming what it can do, \
                     then write `tool: {tool}/<action>`."
                ),
            },
        ));
        return;
    }
    if !names.contains(&action) {
        diags.push(Diagnostic::error(
            "loader/no-such-action-to-guard",
            entry.node.span.clone(),
            format!(
                "This rule guards '{action}' on '{tool}', and '{tool}' has no action by \
                 that name — so the rule gates nothing and the call it was written about \
                 goes straight through."
            ),
            offer(
                "action",
                action,
                &names,
                &format!("add it under `actions:` in `tools/{tool}.yaml`"),
            ),
        ));
        return;
    }

    // The rule resolves. Now: does the argument it looks at exist, and is the
    // rule allowed to look at it?
    arguments_exist(when, tool, action, actions.and_then(|m| m.get(action)), diags);
}

/// An approval rule reading an argument the action does not declare, or one its
/// `inspects:` list does not admit.
///
/// `inspects:`' own help says it names *"the arguments an approval rule is
/// allowed to look at"*. Until `takes:` existed there was nothing to hold either
/// against, so `arg: ammount` on the money-moving rule loaded clean and the gate
/// compared a figure that was never there — which reads, from the outside,
/// exactly like a refund small enough not to need approval.
fn arguments_exist(
    when: &Node,
    tool: &str,
    action: &str,
    declared: Option<&Entry>,
    diags: &mut Diagnostics,
) {
    let Some(arg_entry) = when.as_map().and_then(|m| m.get("arg")) else { return };
    let Some(arg) = arg_entry.node.as_str().map(str::trim) else { return };
    let Some(declared) = declared else { return };

    let takes: Vec<&str> = declared
        .node
        .get("takes")
        .and_then(Node::as_map)
        .map(|m| m.keys().map(String::as_str).collect())
        .unwrap_or_default();
    if takes.is_empty() {
        return; // nothing declared to hold it against — a different, quieter gap
    }
    if !takes.contains(&arg) {
        diags.push(Diagnostic::error(
            "loader/no-such-argument-to-look-at",
            arg_entry.node.span.clone(),
            format!(
                "This rule looks at '{arg}', and `{tool}/{action}` is never given anything \
                 by that name — so the comparison is against nothing and a person is never \
                 asked."
            ),
            offer(
                "arg",
                arg,
                &takes,
                &format!("add it under `takes:` for `{action}` in `tools/{tool}.yaml`"),
            ),
        ));
        return;
    }

    let inspects: Vec<&str> = declared
        .node
        .get("inspects")
        .and_then(Node::as_list)
        .map(|l| l.iter().filter_map(Node::as_str).map(str::trim).collect())
        .unwrap_or_default();
    if !inspects.is_empty() && !inspects.contains(&arg) {
        // An ERROR, and it says what really happens. It was a warning — so
        // `pact check` printed the sentence and exited 0 — and the sentence
        // claimed a runtime consequence that did not happen at all: nothing on
        // the executing side had ever read `inspects:`, so the rule went on
        // comparing whatever it liked and the line was decoration. Its sibling
        // one branch up, `loader/no-such-argument-to-look-at`, has been an error
        // for the same stated consequence all along.
        //
        // The consequence is real now, and it is the opposite of "nobody is
        // asked": `questions._atom_stops` refuses to read an argument the action
        // does not offer, and a condition PACT may not evaluate STOPS the call —
        // the same way a malformed `more-than:` already does, and for the same
        // reason, that turning a mistake into a disabled gate is the one
        // direction this whole area must never fail in. So the author's figure
        // stops governing and every call waits. That is safe and it is not what
        // they wrote, which is why it is refused here rather than reported after
        // the run.
        diags.push(Diagnostic::error(
            "loader/argument-not-offered-for-inspection",
            arg_entry.node.span.clone(),
            format!(
                "This rule looks at '{arg}', and `{action}` offers only {} for a rule to \
                 look at — so the figure you wrote governs nothing, and every call to \
                 `{action}` stops and asks instead of only the ones over it.",
                inspects.join(", ")
            ),
            format!(
                "Add `{arg}` to the `inspects:` line for `{action}` in \
                 `tools/{tool}.yaml`, or change this rule to look at one of: {}.",
                inspects.join(", ")
            ),
        ));
    }
}

/// The list of what does exist, and the thing to do about a name that is
/// genuinely new. Never "one of: " with nothing after it.
fn offer(field: &str, _wrote: &str, known: &[&str], add: &str) -> String {
    if known.is_empty() {
        let mut instruction = add.replace("{}", "your-tool").to_string();
        if let Some(head) = instruction.get_mut(..1) {
            head.make_ascii_uppercase();
        }
        return format!("Nothing is declared there yet. {instruction}.");
    }
    format!("Change the `{field}:` to one of: {}.", known.join(", "))
}

/// The span of a key, so a diagnostic underlines the setting rather than the
/// whole block.
fn key_span(node: &Node, field: &str) -> Option<Span> {
    node.as_map().and_then(|m: &Map| m.get(field)).map(|e: &Entry| e.key_span.clone())
}

// ─────────────────────────────────────────── `needs-a-person: yes` (F17)
//
// **The shorthand, desugared where approvals are already resolved.**
//
// Gating one action used to cost three files and thirteen lines: a question, a
// policy file, and a rule inside it. Eve charges one file and two lines for the
// same gate (`approval: 'always'` beside the tool), and a measured first-time
// author needed four rounds of diagnostics — and four concepts — before their
// first gate held. That is the one surface where this format is harder to author
// in than the system it has to beat.
//
// So `needs-a-person: yes` on an action expands, here, to exactly the rule the
// author would otherwise have typed:
//
//     when:     [{ tool: <tool>/<action> }]
//     because:  built from the action's own `description:`
//     question: pact:question/is-this-ok      (spec/questions/is-this-ok.yaml)
//
// Nothing downstream learns a new shape. [`report::LoadReport`] pushes these
// onto the same `waits` list the policy rules produce, so `pact waits` lists a
// gate written the short way beside one written the long way, and a scheduler
// sets the same timer for both.
//
// The whole point is that the guarantee is unchanged. The shipped question
// carries `asked-of:`, `answer-within:` and `if-nobody-answers:` like every
// written one, and the last of those is `stop-and-say-so` — there is no
// spelling of "approve" anywhere on this path either.

/// The question the short form puts, by name.
///
/// The `pact:` prefix is the one `loop:` already uses for a shipped shape
/// (`or-one-of: [pact:loop/standard]`), so an author who has met one has met
/// this. It cannot collide with a name in `questions/`: a file called
/// `pact:question/is-this-ok.yaml` is not a filename.
pub const SHIPPED_QUESTION: &str = "pact:question/is-this-ok";

/// The shipped question, as data, from the file an author can read.
///
/// `include_str!` rather than a literal in Rust for the reason
/// `BUILTIN_SPEC` and `BUILTIN_CATALOGUE` are: one copy, so a wording change in
/// `spec/questions/is-this-ok.yaml` cannot fail to reach the binary. (The Python
/// side keeps its own copy for invariant P-1 — an adapter reads the loaded
/// document, never the tree — and `test_a_gate_written_in_one_line.py` holds the
/// two against each other the way `test_loops.py` does for the shipped loops.)
pub fn shipped_question() -> &'static Node {
    static PARSED: std::sync::OnceLock<Node> = std::sync::OnceLock::new();
    PARSED.get_or_init(|| {
        const TEXT: &str = include_str!("../../../spec/questions/is-this-ok.yaml");
        pact_doc::parse_yaml(TEXT, camino::Utf8Path::new("spec/questions/is-this-ok.yaml"))
            .expect("the question PACT ships parses — it is checked by a test of its own")
    })
}

/// One action gated by the short line, expanded into what a rule would say.
#[derive(Debug, Clone, PartialEq)]
pub struct Desugared {
    /// The tool the action belongs to.
    pub tool: String,
    /// The action itself. `<tool>/<action>` is what a written rule's `when:`
    /// would hold.
    pub action: String,
    /// The `needs-a-person:` line itself, so a person told "this run is waiting"
    /// can open the file that decided it would — exactly as a policy rule's
    /// `question:` line is what a long-form wait points at.
    pub declared_at: Span,
    /// Why a person is being asked, in the action's own words. This is what the
    /// approver reads under `why:`, and it is the difference between a real
    /// screen and a placeholder: the shipped question cannot know which action
    /// it is about, so the desugaring tells it.
    pub because: String,
    /// The values to put in front of the person — every argument the action
    /// declares under `takes:`. The long form makes the author list these; the
    /// short form reads them off the action, because the action already says
    /// what it is given.
    pub shows: Vec<String>,
}

impl Desugared {
    /// `payments/issue-refund` — the spelling a written rule's `when:` uses.
    pub fn named(&self) -> String {
        format!("{}/{}", self.tool, self.action)
    }
}

/// Every action in the workspace whose own file says it needs a person.
///
/// Actions whose gate a POLICY RULE already decides are left out, which is the
/// whole of "the expert path wins": a rule says who is asked, how long they
/// have and what shape the answer takes, and a shorthand quietly adding a
/// second wait beside it would put two screens in front of one person for one
/// call. [`shorthand_and_rule_do_not_both_decide`] tells the author where that
/// happened, so the line they wrote is never silently ignored.
pub fn desugared(document: &Node) -> Vec<Desugared> {
    let Some(tools) = document.get("tools").and_then(Node::as_map) else { return Vec::new() };
    let already = ruled_on(document);
    let mut out = Vec::new();
    for (tool, entry) in tools {
        let Some(actions) = entry.node.get("actions").and_then(Node::as_map) else { continue };
        for (action, a) in actions {
            if !asked_for(&a.node) || already.contains(&format!("{tool}/{action}")) {
                continue;
            }
            out.push(Desugared {
                tool: tool.clone(),
                action: action.clone(),
                declared_at: key_span(&a.node, "needs-a-person")
                    .unwrap_or_else(|| a.node.span.clone()),
                because: because_of(tool, action, &a.node),
                shows: a
                    .node
                    .get("takes")
                    .and_then(Node::as_map)
                    .map(|m| m.keys().cloned().collect())
                    .unwrap_or_default(),
            });
        }
    }
    out
}

/// The same, narrowed to the actions ONE agent can actually call.
///
/// Through `uses:`, the way a connection consent is found — an agent that
/// cannot reach `payments` does not wait for a person about it. The long form
/// binds through `policies:` and `applies-to:`; this binds through the tool,
/// which is stricter and needs no line from the author to say so.
pub fn desugared_for(document: &Node, agent: &Node) -> Vec<Desugared> {
    let mut reachable: Vec<String> = match agent.get("uses") {
        Some(n) => match n.as_str() {
            Some(one) => vec![one.trim().to_string()],
            None => n
                .as_list()
                .map(|l| l.iter().filter_map(Node::as_str).map(|s| s.trim().to_string()).collect())
                .unwrap_or_default(),
        },
        None => Vec::new(),
    };
    reachable.sort();
    desugared(document).into_iter().filter(|g| reachable.contains(&g.tool)).collect()
}

/// Does this action's own file say a person has to say yes?
///
/// Through the schema's own yes/no reader, the way `money::moves_money` reads
/// `spends-money:` and for the identical reason: `yes`, `y`, `true`, `on` and
/// `enabled` are all a yes to the validator, so all five have to be a yes here.
/// A tick this did not recognise would be an authored gate that loads clean and
/// stops nothing.
pub fn asked_for(action: &Node) -> bool {
    let Some(written) = action.get("needs-a-person") else { return false };
    matches!(
        pact_schema::coerce::check(written, &pact_schema::Ty::YesNo),
        Some(pact_schema::coerce::Coerced::YesNo(true))
    )
}

/// `why:` on the approver's screen, in the action's own words.
///
/// A person asked to approve something has to be told what it is. The shipped
/// question's `says:` is fixed wording that cannot name an action, so this is
/// where the action gets named — and it is named from `description:`, which the
/// author already wrote for the model to read.
fn because_of(tool: &str, action: &str, node: &Node) -> String {
    let described = node.get("description").and_then(Node::as_str).map(str::trim).unwrap_or("");
    if described.is_empty() {
        return format!("`{action}` on `{tool}` needs a person before it runs.");
    }
    let described = described.trim_end_matches('.');
    format!("`{action}` on `{tool}` needs a person before it runs — it does this: {described}.")
}

/// Every `<tool>/<action>` a written approval rule already decides.
fn ruled_on(document: &Node) -> std::collections::BTreeSet<String> {
    let mut out = std::collections::BTreeSet::new();
    let Some(policies) = document.get("policies").and_then(Node::as_map) else { return out };
    for (_, policy) in policies {
        let Some(rules) = policy.node.get("ask-a-person").and_then(Node::as_list) else { continue };
        for rule in rules {
            for when in rule.get("when").and_then(Node::as_list).into_iter().flatten() {
                let Some(named) = when.get("tool").and_then(Node::as_str).map(str::trim) else {
                    continue;
                };
                out.insert(named.to_string());
            }
        }
    }
    out
}

/// The short line and a written rule about the SAME action.
///
/// Not an error: both are legitimate lines and the tree is valid. It is
/// reported because the short line stops doing anything the moment the rule
/// exists, and an authoring field that is read by nobody is the defect this
/// whole area keeps producing. The rule wins — it is the one that can say who is
/// asked, how long they have and what shape the answer takes — but the author
/// has to be the one who knows that, not find out from a run.
fn shorthand_and_rule_do_not_both_decide(document: &Node, diags: &mut Diagnostics) {
    let ruled = ruled_on(document);
    if ruled.is_empty() {
        return;
    }
    let Some(tools) = document.get("tools").and_then(Node::as_map) else { return };
    for (tool, entry) in tools {
        let Some(actions) = entry.node.get("actions").and_then(Node::as_map) else { continue };
        for (action, a) in actions {
            if !asked_for(&a.node) || !ruled.contains(&format!("{tool}/{action}")) {
                continue;
            }
            let span =
                key_span(&a.node, "needs-a-person").unwrap_or_else(|| a.node.span.clone());
            diags.push(Diagnostic::warning(
                "loader/asked-for-twice",
                span,
                format!(
                    "`{action}` on `{tool}` says `needs-a-person: yes`, and a rule in \
                     `policies/` also asks a person about it. The rule is the one that \
                     runs — it says who is asked, how long they have and what counts as an \
                     answer — so this line changes nothing here."
                ),
                format!(
                    "Delete `needs-a-person: yes` from the `{action}` block, and the rule \
                     goes on gating it. Delete the rule instead if the short line is what \
                     you meant — then whoever is running the agent is asked, for thirty \
                     minutes, and the run stops if nobody answers."
                ),
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("policies.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        check(&node, &mut d);
        d
    }

    const WORKSPACE: &str = "
tools:
  payments:
    description: Where refunds are issued.
    actions:
      issue-refund:
        description: Send money back.
        takes:
          amount: money
        inspects: [amount]
policies:
  approvals:
    ask-a-person:
      - when:
          - { tool: payments/issue-refund, arg: amount, more-than: 200 USD }
        because: a refund over 200 USD is a management decision
        question: is-this-ok
";

    #[test]
    fn a_rule_naming_a_real_action_of_a_real_tool_is_left_alone() {
        let d = check_text(WORKSPACE);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_misspelt_tool_on_the_money_path_is_refused_where_the_author_is() {
        let d = check_text(&WORKSPACE.replace("payments/issue-refund", "paymnets/issue-refund"));
        let e = d.items().iter().find(|x| x.rule == "loader/no-such-tool-to-guard").expect("caught");
        assert!(e.message.contains("paymnets"), "{}", e.message);
        assert!(e.fix.contains("payments"), "the fix must name what exists: {}", e.fix);
    }

    #[test]
    fn a_misspelt_action_is_refused_and_the_real_ones_are_listed() {
        let d = check_text(&WORKSPACE.replace("issue-refund, arg", "issue-refudn, arg"));
        let e =
            d.items().iter().find(|x| x.rule == "loader/no-such-action-to-guard").expect("caught");
        assert!(e.fix.contains("issue-refund"), "{}", e.fix);
    }

    #[test]
    fn a_rule_that_names_a_tool_and_no_action_is_told_it_gates_nothing() {
        let d = check_text(&WORKSPACE.replace("payments/issue-refund", "payments"));
        let e = d.items().iter().find(|x| x.rule == "loader/rule-names-no-action").expect("caught");
        assert!(e.fix.contains("payments/issue-refund"), "the fix is a line to type: {}", e.fix);
    }

    #[test]
    fn a_rule_reading_an_argument_the_action_never_gets_is_refused() {
        let d = check_text(&WORKSPACE.replace("arg: amount", "arg: ammount"));
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/no-such-argument-to-look-at")
            .expect("a comparison against nothing must be caught");
        assert!(e.message.contains("ammount"));
        assert!(e.fix.contains("amount"), "{}", e.fix);
    }

    #[test]
    fn a_rule_looking_at_an_argument_the_action_does_not_offer_is_refused_not_merely_noted() {
        // The rule had no test at all, and was a WARNING — so `pact check`
        // printed the sentence and exited 0 — while its sibling one branch up,
        // for the same stated consequence, has always been an error. Both halves
        // are held here: that it is refused, and that the sentence says what the
        // gate now really does.
        let two_arguments = WORKSPACE.replace(
            "        takes:\n          amount: money\n",
            "        takes:\n          amount: money\n          order-number: text\n",
        );
        let d = check_text(&two_arguments.replace("arg: amount", "arg: order-number"));
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/argument-not-offered-for-inspection")
            .unwrap_or_else(|| panic!("a gate reading what it may not must be caught:\n{}", d.render()));
        assert_eq!(
            e.severity,
            pact_diag::Severity::Error,
            "a warning exits 0, and this line is on the path where money moves"
        );
        assert!(e.message.contains("order-number"), "{}", e.message);
        assert!(
            e.message.contains("stops and asks"),
            "the sentence has to say what really happens now, not the opposite: {}",
            e.message
        );
        assert!(
            e.fix.contains("`inspects:`") && e.fix.contains("amount"),
            "the fix has to be typeable, both ways round: {}",
            e.fix
        );
    }

    #[test]
    fn an_action_that_offers_nothing_for_inspection_leaves_every_rule_over_it_alone() {
        // The permission is the AUTHOR'S line. Most tool files have not written
        // one, and enforcing an absent line would refuse rules that are correct
        // today — which is why `_inspects_of` on the executing side leaves such
        // an action out of the map entirely rather than mapping it to nothing.
        let d = check_text(&WORKSPACE.replace("        inspects: [amount]\n", ""));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_workspace_with_no_policies_is_not_walked_at_all() {
        let d = check_text("agents:\n  desk:\n    description: x\n");
        assert!(d.is_empty(), "{}", d.render());
    }
}

#[cfg(test)]
mod binding_tests {
    use super::*;
    use pact_doc::parse_yaml;

    const TREE: &str = "
agents:
  desk:
    run-inputs:
      customer-id: text
    uses: [payments]
tools:
  payments:
    actions:
      issue-refund:
        bind: { customer-id: run-inputs.customer-id }
";

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("w.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        check(&node, &mut d);
        d
    }

    #[test]
    fn a_binding_that_names_a_real_run_input_is_left_alone() {
        assert!(check_text(TREE).is_empty(), "{}", check_text(TREE).render());
    }

    #[test]
    fn a_misspelt_run_input_is_refused_because_the_model_would_choose_it_instead() {
        let d = check_text(&TREE.replace("run-inputs.customer-id }", "run-inputs.custommer-id }"));
        let e = d.items().first().expect("caught");
        assert_eq!(e.rule, "loader/no-such-run-input");
        assert!(e.fix.contains("customer-id"), "the fix must name what exists: {}", e.fix);
    }

    #[test]
    fn a_binding_from_a_namespace_that_does_not_exist_is_refused_by_shape() {
        let d = check_text(&TREE.replace("run-inputs.customer-id }", "whatever.i.like }"));
        let e = d.items().first().expect("caught");
        assert_eq!(e.rule, "loader/not-a-binding");
        assert!(e.fix.contains("run-inputs."), "{}", e.fix);
    }
}
