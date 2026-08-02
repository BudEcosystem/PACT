//! **`shows:` held against the parks that move money.**
//!
//! `question.shows:` names the values to put in front of the person deciding.
//! `Question.about_call` filters them with `if k in args`, so a name nothing
//! there supplies simply vanishes — at check time and again at run time, with
//! nothing anywhere saying so. `loader/shows-nothing-can-supply` was written to
//! end that, and it reached three of the five parks.
//!
//! The two it did not reach were the two that MOVE MONEY. Measured on the worked
//! example with `shows: [banana]` written into each question file in turn:
//!
//! | file | park | `pact check` said |
//! |---|---|---|
//! | `questions/keep-going.yaml` | a ceiling | warning, with the real names listed |
//! | `questions/too-long-to-send.yaml` | a long conversation | warning, likewise |
//! | `questions/is-this-ok.yaml` | **the approval before a refund** | *"OK — loaded cleanly"*, exit 0 |
//! | `questions/may-we-connect.yaml` | **consent to spend over a connection** | *"OK — loaded cleanly"*, exit 0 |
//!
//! The reason was in the code and had expired. An action park was written as
//! `OPEN` — no list of names, so no name could be called wrong — and that was
//! true when it was written. `takes:` landed since: the action now says what it
//! is given, so the list was never missing, it was only never asked for.
//!
//! Every test here edits the worked example's own YAML and reads the diagnostics
//! back. A test that assembled a document in Rust would prove the comparison
//! works and say nothing about whether the author's line reaches it.

use camino::Utf8PathBuf;
use pact_diag::Diagnostics;
use pact_doc::Node;
use pact_loader::Loader;
use pact_loader::report::LoadReport;

fn example() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples/refund-desk")
}

fn read(root: &Utf8PathBuf) -> (Node, Diagnostics) {
    let mut d = Diagnostics::new();
    let node = Loader::new(root.clone()).load(root, &mut d).expect("the example loads");
    let _ = LoadReport::of(&node, &mut d);
    d.sort();
    (node, d)
}

/// A throwaway copy of the worked example with one line of one file replaced.
fn the_example_with(why: &str, file: &str, from: &str, to: &str) -> Utf8PathBuf {
    let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
        .join(format!("pact-money-parks-{why}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    copy_tree(&example(), &base);
    let path = base.join(file);
    let text = std::fs::read_to_string(&path).unwrap_or_else(|_| panic!("{file} is there"));
    assert!(text.contains(from), "the line this test edits must exist in {file}: {from}");
    std::fs::write(&path, text.replacen(from, to, 1)).unwrap();
    base
}

fn copy_tree(from: &Utf8PathBuf, to: &Utf8PathBuf) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap().flatten() {
        let name = entry.file_name().into_string().unwrap();
        let (src, dst) = (from.join(&name), to.join(&name));
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&src, &dst);
        } else {
            std::fs::copy(&src, &dst).unwrap();
        }
    }
}

fn only(diags: &Diagnostics, rule: &str) -> Vec<pact_diag::Diagnostic> {
    diags.items().iter().filter(|d| d.rule == rule).cloned().collect()
}

#[test]
fn a_value_the_approval_before_a_refund_cannot_show_is_reported_where_the_author_wrote_it() {
    // `questions/is-this-ok.yaml` is put by two rules of
    // `policies/approvals.yaml`, and this is the one that stops money. Before
    // this the same edit printed "OK — … loaded cleanly" and exited 0, so the
    // author had named a value for the approver to see and the approver saw
    // nothing.
    let root = the_example_with("approval", "questions/is-this-ok.yaml", "- amount", "- banana");
    let (_, diags) = read(&root);

    let [warn] = &only(&diags, "loader/shows-nothing-can-supply")[..] else {
        panic!("one name, one message:\n{}", diags.render());
    };
    assert_eq!(warn.span.file.file_name(), Some("is-this-ok.yaml"));
    assert!(warn.span.line > 1, "a diagnostic has to name the line, not just the file");
    assert!(warn.message.contains("banana"), "{}", warn.message);
    // The list comes off `tools/payments.yaml` and `tools/zendesk.yaml` — the
    // `takes:` of the actions those two rules name — so it is the author's own
    // words back at them and not a table kept here.
    for real in ["amount", "order-number", "message", "ticket-id"] {
        assert!(warn.fix.contains(real), "the fix must list what does work: {}", warn.fix);
    }

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_value_the_consent_to_use_a_connection_cannot_show_is_reported_too() {
    // The other money park. `resources/payments-server.yaml` says
    // `asks-to-connect: may-we-connect`, and that consent is what stands between
    // this desk and a payments system it may be billed by. It has no `when:` at
    // all — it stops every call to `payments` — so what a person can be shown is
    // every action of that tool, and `banana` is not one of them.
    let root =
        the_example_with("consent", "questions/may-we-connect.yaml", "- order-number", "- banana");
    let (_, diags) = read(&root);

    let [warn] = &only(&diags, "loader/shows-nothing-can-supply")[..] else {
        panic!("the connection consent must be checked like any other park:\n{}", diags.render());
    };
    assert_eq!(warn.span.file.file_name(), Some("may-we-connect.yaml"));
    assert!(warn.message.contains("banana"), "{}", warn.message);
    assert!(warn.fix.contains("amount") && warn.fix.contains("order-number"), "{}", warn.fix);

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_names_are_read_off_the_action_so_deleting_its_takes_block_stops_the_check() {
    // The list is DERIVED, and this is what proves it rather than a table living
    // in Rust that happens to agree with the example. Take `takes:` off
    // `issue-refund` and `banana` stops being refusable at the refund park —
    // there is no longer anything to hold it against, and the module's own rule
    // is that refusing a legitimate name is worse than the silence.
    //
    // The `zendesk/reply` rule still has its `takes:`, so the question is still
    // checked through that binding; what changes is that the vocabulary no
    // longer closes. Both rules lose theirs here, one file at a time.
    let root = the_example_with(
        "no-takes",
        "questions/is-this-ok.yaml",
        "- amount",
        "- banana",
    );
    for (file, block) in [
        ("tools/payments.yaml", "    takes:\n      order-number: text\n      amount: money\n"),
        ("tools/zendesk.yaml", "    takes:\n      ticket-id: text\n      message: text\n"),
    ] {
        let path = root.join(file);
        let text = std::fs::read_to_string(&path).unwrap();
        assert!(text.contains(block), "the block this test deletes must exist in {file}");
        std::fs::write(&path, text.replacen(block, "", 1)).unwrap();
    }

    let (_, diags) = read(&root);
    assert!(
        only(&diags, "loader/shows-nothing-can-supply").is_empty(),
        "with no `takes:` there is no list, and an absent list must never be read as an \
         empty one:\n{}",
        diags.render()
    );

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_rule_naming_a_tool_that_is_not_there_leaves_the_shows_lines_alone() {
    // A picture with a hole in it is not a list to refuse an author's line
    // against. Misspelling the tool in the money rule is a real mistake and is
    // reported at the line the author typed, by `loader/no-such-tool-to-guard` —
    // and following a SECOND diagnostic telling them to change `shows:` would
    // have them edit a file that has nothing wrong with it.
    let root = the_example_with(
        "dangling",
        "policies/approvals.yaml",
        "payments/issue-refund, arg: amount, more-than: 200 USD",
        "paymnets/issue-refund, arg: amount, more-than: 200 USD",
    );
    // Both checks, because `pact check` runs both and the author reads one
    // screen. The tool name is `approvals::check`'s to resolve; the `shows:`
    // names are this module's.
    let mut diags = Diagnostics::new();
    let doc = Loader::new(root.clone()).load(&root, &mut diags).expect("still loads");
    pact_loader::approvals::check(&doc, &mut diags);
    let _ = LoadReport::of(&doc, &mut diags);
    diags.sort();

    assert!(
        !only(&diags, "loader/no-such-tool-to-guard").is_empty(),
        "the real mistake still has to be reported:\n{}",
        diags.render()
    );
    assert!(
        only(&diags, "loader/shows-nothing-can-supply").is_empty()
            && only(&diags, "loader/shows-nothing-at-this-park").is_empty(),
        "one mistake, one message — the `shows:` lines are not the mistake:\n{}",
        diags.render()
    );

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_question_shared_between_two_money_parks_is_held_against_each_of_them_separately() {
    // Per BINDING, which the rule above cannot be. `is-this-ok` is put before a
    // refund AND before a reply to a customer, and its own first line promises
    // both — *"before money moves or a customer hears from us"*. It named the
    // refund's values only, so the person approving a reply read the wording and
    // nothing else: not the message about to be sent, not the ticket it was on.
    //
    // The example carries all four names now. Take the reply's two away again
    // and the park says so.
    let root = the_example_with(
        "one-park-only",
        "questions/is-this-ok.yaml",
        "  - message\n  - ticket-id\n",
        "",
    );
    let (_, diags) = read(&root);

    let [warn] = &only(&diags, "loader/shows-nothing-at-this-park")[..] else {
        panic!(
            "a park where NONE of the shown values exist is a screen nobody can act \
             on:\n{}",
            diags.render()
        );
    };
    assert_eq!(warn.span.file.file_name(), Some("is-this-ok.yaml"));
    assert!(
        warn.fix.contains("message") && warn.fix.contains("ticket-id"),
        "the fix has to name what THAT park supplies: {}",
        warn.fix
    );

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn one_policy_covering_three_agents_is_one_mistake_and_one_message() {
    // `policies/approvals.yaml` says `applies-to: every-agent`, so its
    // `zendesk/reply` rule binds `is-this-ok` once per agent — three bindings for
    // one line in one file. Three copies of a warning is three things to fix for
    // one edit, which is the noise `check_deadline` one function down is
    // deduplicated to avoid, and this check acquired it the moment those parks
    // stopped being exempt.
    let root = the_example_with(
        "three-agents",
        "questions/is-this-ok.yaml",
        "  - message\n  - ticket-id\n",
        "",
    );
    let (doc, diags) = read(&root);
    let agents = doc.get("agents").and_then(Node::as_map).expect("the example has agents");
    assert!(agents.len() >= 3, "this test needs the policy to cover several agents");
    assert_eq!(only(&diags, "loader/shows-nothing-at-this-park").len(), 1, "{}", diags.render());

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_worked_examples_own_shows_lines_are_all_names_their_parks_really_supply() {
    // The floor. Every check above is only worth having if the shipped tree
    // passes it — and it did not: closing the two money parks found that
    // `is-this-ok` showed an amount and an order number at a park that has
    // neither, which is why `questions/is-this-ok.yaml` now names the reply's
    // arguments too.
    let (_, diags) = read(&example());
    for rule in ["loader/shows-nothing-can-supply", "loader/shows-nothing-at-this-park"] {
        assert!(only(&diags, rule).is_empty(), "{}", diags.render());
    }
}
