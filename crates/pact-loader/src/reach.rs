//! **A tool that reaches nowhere, and a tool that reaches two places.**
//!
//! A `tool` says where it goes on exactly one line: `connect:` names a server in
//! `resources:`, `url:` names an address, `says:` puts the question to a model.
//! Until this module, nothing anywhere held a tool to writing one of them.
//!
//! `runs-as:` looked like it did. It was a word with four choices sitting in
//! front of those three lines, and it was read by nothing — not the loader, not
//! an adapter, not the worked example, which has never written it. Two of its
//! choices (`prompt`, `built-in`) named ways of running that nothing in this
//! distribution carries out, so a tool written either way was still offered to
//! the model and came back `error: no tool named ...` on the first call, with no
//! diagnostic at check time and nothing on the run's own list of what it could
//! not enforce. It is deleted (R60), and the question it pretended to answer is
//! asked here instead — of the lines that really carry it.
//!
//! Reproduced before this module, on the shipped worked example: deleting
//! `connect: payments-server` from `examples/refund-desk/tools/payments.yaml`
//! printed *"OK — examples/refund-desk loaded cleanly (491 settings)."* and
//! exited 0, and a run then answered every refund with `error: no tool named
//! 'payments'`. Adding a second line — `url:` beside the `connect:` that is
//! already there — printed the same success, and which of the two a runtime
//! would use was decided by nothing written down anywhere.
//!
//! # Why the schema cannot state it
//!
//! `needs-also:` and `needed-when:` both fire on ONE field: this one is set, so
//! that one is owed. *"Exactly one of these three"* is a statement about a set —
//! it has to count what is present and refuse both directions of being wrong,
//! and a field can say neither of those things about its siblings. Writing it as
//! three `needed-when:` rules would also state it three times, which is three
//! chances for the next person to change two of them.
//!
//! # An error, not a warning
//!
//! `money.rs` and `unnamed.rs` warn, because an ungated spend and an unattached
//! policy can both be what somebody meant. Neither shape here can be. A tool
//! with no transport line can never run — there is no reading of the file under
//! which it works — and a tool with two has no answer at all to *which one*, so
//! two runtimes reading the same folder may legitimately do different things,
//! which is the one thing a portable artifact may not permit.
//!
//! # What it deliberately stays quiet about
//!
//! * A `connect:` naming a server this workspace has not got says nothing here.
//!   `names: resources` already refuses that at the line the author typed, and
//!   *"this tool reaches nowhere"* is a strange second thing to read when you
//!   have just misspelled a server's name — the tool does say where it reaches.
//! * A `url:` with no `method:` beside it says nothing here either: that is one
//!   field owing another, which is exactly what `needs-also:` is for, and the
//!   schema states it on `url:` itself.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;

/// The three lines that say where a tool reaches, in the order the schema
/// writes them, with the phrase a diagnostic uses for each.
///
/// Data rather than three branches, because the sentences differ only in which
/// names they carry — and because a fourth transport should cost a row here and
/// a row in the schema, never a new shape of message.
const WAYS: &[(&str, &str)] = &[
    ("connect", "a server in `resources:`"),
    ("url", "an address"),
    ("says", "a model"),
];

/// Refuse every tool that does not name exactly one place to reach.
///
/// Takes the loaded document and nothing else — the same purity `money::check`
/// keeps, and the reason this can run beside every other check in one pass.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let Some(tools) = document.get("tools").and_then(Node::as_map) else {
        return;
    };

    for (name, entry) in tools {
        // A tool that is not a set of settings at all — `payments: see the wiki`
        // — has no lines to count, and the schema already says so in the words
        // that fit ("should be a set of settings"). Counting to nought here as
        // well would be two messages for one mistake, and the second would send
        // the reader adding a `connect:` line to something that is not a block.
        let Some(fields) = entry.node.as_map() else {
            continue;
        };
        // A file whose contents the loader never read says nothing about what
        // is inside it, so nothing about what is inside it is checked — the
        // guard `ports::check` already carries, at the seam that needs it just
        // as much. Measured without it, on a workspace whose only mistake is
        // one unclosed bracket in `tools/broken.yaml`:
        //
        //     error: 'broken' does not say where it reaches: it has no
        //            `connect:`, no `url:` and no `says:`.
        //       fix: Add ONE line to this file …
        //     error: This file is not written correctly: while parsing a flow
        //            sequence, expected ',' or ']'
        //
        // — two errors for one mistake, and the first tells the author to add a
        // line to a file that did not parse. CHK-12 is the rule; this was one of
        // the places it had not reached. It is also what makes the SKIPPED tool
        // in `Loader::classify` cost one message rather than two, since both
        // arrive here as the same placeholder.
        if fields.get(pact_doc::UNLOADED).is_some() {
            continue;
        }
        let written: Vec<&(&str, &str)> = WAYS
            .iter()
            .filter(|(field, _)| {
                fields
                    .get(*field)
                    .and_then(|e| e.node.as_str())
                    .is_some_and(|v| !v.trim().is_empty())
            })
            .collect();

        match written.as_slice() {
            [] => diags.push(Diagnostic::error(
                "loader/tool-reaches-nowhere",
                // The tool's own key, so the underline lands on the name in a
                // workspace written as one file and on the file itself when
                // `tools/` is a folder — which is the shape the worked example
                // has and the shape an author meets first.
                entry.key_span.clone(),
                format!(
                    "'{name}' does not say where it reaches: it has no `connect:`, no `url:` \
                     and no `says:`. The model is still offered it, and every call to it comes \
                     back `error: no tool named '{name}'`."
                ),
                "Add ONE line to this file: `connect: <the name of a server in resources>` to \
                 reach a connected system, or `url: <the address>` with `method: post` beside \
                 it to call an address, or `says: <the wording>` to put the question to a \
                 model."
                    .to_string(),
            )),
            [_] => {}
            _ => {
                // Reported at the SECOND line, with the first shown beside it —
                // the shape `loader/ambiguous-field` already uses for one
                // setting written twice, because the reader's next act is the
                // same: look at both, keep one.
                let first = &written[0];
                let extra = &written[1];
                let at = fields.get(extra.0).map_or_else(
                    || entry.key_span.clone(),
                    |e| e.key_span.clone().merge(&e.node.span),
                );
                let also = fields
                    .get(first.0)
                    .map_or_else(|| entry.key_span.clone(), |e| e.key_span.clone());
                let all: Vec<String> = written
                    .iter()
                    .map(|(field, _)| format!("`{field}:`"))
                    .collect();
                diags.push(
                    Diagnostic::error(
                        "loader/tool-reaches-two-places",
                        at,
                        format!(
                            "'{name}' names {} places to reach — {} are {} set — so nothing \
                             here decides whether a call goes to {} or to {}.",
                            if all.len() == 2 { "two" } else { "three" },
                            and_list(&all),
                            if all.len() == 2 { "both" } else { "all" },
                            first.1,
                            extra.1
                        ),
                        format!(
                            "Keep one. Delete `{}:` from this file, or delete `{}:` — a tool \
                             reaches one place, and a second tool file is how one agent reaches \
                             two.",
                            extra.0, first.0
                        ),
                    )
                    .with_related(also, "already set here"),
                );
            }
        }
    }
}

/// `a and b`, `a, b and c` — a list the way a sentence carries one.
///
/// The same shape `money.rs` uses for the agents that reach an ungated spend,
/// and for the same reason: a reader should not have to tell two conventions
/// apart inside one sentence.
fn and_list(names: &[String]) -> String {
    match names.split_last() {
        None => String::new(),
        Some((last, [])) => last.clone(),
        Some((last, rest)) => format!("{} and {last}", rest.join(", ")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    /// The shape the worked example has: one tool reaching one server, with the
    /// actions it is allowed to call.
    const WORKSPACE: &str = "
tools:
  payments:
    description: Where refunds are issued.
    connect: payments-server
    actions:
      issue-refund:
        description: Send money back.
";

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("workspace.yaml", text);
        check(&node, &mut d);
        d
    }

    fn only(d: &Diagnostics) -> &Diagnostic {
        assert_eq!(
            d.items().len(),
            1,
            "expected exactly one diagnostic:\n{}",
            d.render()
        );
        &d.items()[0]
    }

    #[test]
    fn a_tool_that_names_one_place_to_reach_is_left_alone() {
        // The half that matters most: a correct tree must not be refused. A
        // false positive on the shipped shape costs an author their trust in
        // every other line the tool prints.
        assert!(
            check_text(WORKSPACE).is_empty(),
            "{}",
            check_text(WORKSPACE).render()
        );
    }

    #[test]
    fn each_of_the_three_ways_to_reach_somewhere_counts_on_its_own() {
        for line in [
            "connect: payments-server",
            "url: host/payments-api",
            "says: Refund this.",
        ] {
            let text = WORKSPACE.replace("connect: payments-server", line);
            assert!(
                check_text(&text).is_empty(),
                "{line} is a way to reach: {}",
                check_text(&text).render()
            );
        }
    }

    #[test]
    fn a_tool_with_no_way_to_reach_anything_is_refused_and_the_three_lines_are_offered() {
        let d = check_text(&WORKSPACE.replace("    connect: payments-server\n", ""));
        let e = only(&d);
        assert_eq!(e.rule, "loader/tool-reaches-nowhere");
        assert_eq!(
            e.severity,
            pact_diag::Severity::Error,
            "no reading of the file makes it work"
        );
        assert!(
            e.message
                .contains("no `connect:`, no `url:` and no `says:`"),
            "{}",
            e.message
        );
        assert!(
            e.message.contains("error: no tool named 'payments'"),
            "the sentence has to name what the author would otherwise only see at run time: {}",
            e.message
        );
        for typeable in ["connect: ", "url: ", "method: post", "says: "] {
            assert!(
                e.fix.contains(typeable),
                "the fix must be typeable ({typeable}): {}",
                e.fix
            );
        }
    }

    #[test]
    fn a_tool_that_names_two_places_is_refused_and_both_are_named() {
        let d = check_text(&WORKSPACE.replace(
            "connect: payments-server",
            "connect: payments-server\n    url: host/payments-api",
        ));
        let e = only(&d);
        assert_eq!(e.rule, "loader/tool-reaches-two-places");
        assert!(
            e.message.contains("`connect:` and `url:`"),
            "both are named: {}",
            e.message
        );
        assert!(e.fix.contains("Delete `url:`"), "a typeable fix: {}", e.fix);
        assert!(
            e.fix.contains("or delete `connect:`"),
            "and the other way round: {}",
            e.fix
        );
    }

    #[test]
    fn the_underline_is_on_the_second_line_and_the_first_is_shown_beside_it() {
        // The reader's next act is to look at both lines and keep one, so both
        // have to be on the screen — the shape `loader/ambiguous-field` uses for
        // one setting written twice.
        let d = check_text(&WORKSPACE.replace(
            "connect: payments-server",
            "connect: payments-server\n    url: host/payments-api",
        ));
        let rendered = d.render();
        assert!(
            rendered.contains("url: host/payments-api"),
            "the line pointed at is shown:\n{rendered}"
        );
        assert!(
            rendered.contains("already set here"),
            "the first is shown beside it:\n{rendered}"
        );
    }

    #[test]
    fn all_three_at_once_is_one_sentence_naming_all_three() {
        let d = check_text(&WORKSPACE.replace(
            "connect: payments-server",
            "connect: payments-server\n    url: host/payments-api\n    says: Refund this.",
        ));
        let e = only(&d);
        assert!(
            e.message.contains("names three places to reach"),
            "{}",
            e.message
        );
        assert!(
            e.message
                .contains("`connect:`, `url:` and `says:` are all set"),
            "all three are named, so the author can see the whole mistake: {}",
            e.message
        );
    }

    #[test]
    fn an_empty_line_is_not_a_way_to_reach_anything() {
        // `connect:` with nothing after it is the commonest half-finished line
        // there is, and reading it as an answer would make this check pass on
        // exactly the file it exists to catch.
        let d = check_text(&WORKSPACE.replace("connect: payments-server", "connect:"));
        assert_eq!(only(&d).rule, "loader/tool-reaches-nowhere");
    }

    #[test]
    fn a_tool_that_is_not_a_set_of_settings_is_left_to_the_check_that_owns_that() {
        // One mistake gets one message. `payments: see the wiki` is already
        // refused by the schema in the words that fit it, and "add a `connect:`
        // line" would send the reader editing something that is not a block.
        let d = check_text("tools:\n  payments: see the wiki\n");
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_workspace_with_no_tools_is_not_walked_at_all() {
        assert!(check_text("agents:\n  desk:\n    description: x\n").is_empty());
    }
}
