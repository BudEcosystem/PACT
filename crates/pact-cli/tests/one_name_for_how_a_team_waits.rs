//! D13 is "one thing, one name", and the place it broke was inside the
//! normative specification itself.
//!
//! Two documents described the same idea — how much of a team has to come back
//! before the parent carries on — in two vocabularies that **disagreed on the
//! default**. `docs/20-ARCHITECTURE-DRAFT.md` §7.3 wrote the edge's join as
//! `mode: all | any | first-ok | all-settled | quorum(k)` and said *"unset
//! `mode` defaults to `any`"*; `spec/schema.yaml` wrote `teamwork.waits-for` as
//! `everyone | anyone | enough-of-them | the-first-good-answer |
//! whoever-answers-in-time` and defaulted to `everyone`. So the same four lines
//! an author typed meant "wait for both" in the harness and "carry on at the
//! first reply" in the graph, and nothing anywhere failed.
//!
//! That is not a bug a reader can find. Prose does not run, so a second
//! vocabulary can sit in a document for revisions, and the only reason this one
//! was caught is that somebody read both files in the same afternoon.
//!
//! So the two documents are held against each other here. The schema is the
//! authored surface and stays the source of truth — it is data, and an author
//! writes it — and §7.3's `join:` is what §7.7 desugars that surface **to**.
//! This file fails when the two sets of words stop being the same set.
//!
//! It reads the same way `deliberate_refusals.rs` and `eve_inventory.rs` do —
//! walk the Markdown, walk the YAML by line — because both files are read by
//! people first and have to stay readable to them.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn arch() -> String {
    let p = repo().join("docs/20-ARCHITECTURE-DRAFT.md");
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

fn schema() -> String {
    let p = repo().join("spec/schema.yaml");
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

/// The body of one `### <number> …` section of the architecture draft.
fn section(number: &str) -> String {
    let text = arch();
    let opener = format!("### {number} ");
    let body = text
        .split(&opener)
        .nth(1)
        .unwrap_or_else(|| panic!("the architecture draft has no §{number}"));
    let body = body.split("\n### ").next().unwrap_or(body);
    body.to_string()
}

/// Every ```` ```yaml ```` block inside a stretch of Markdown, in order.
fn yaml_blocks(markdown: &str) -> Vec<String> {
    markdown
        .split("```yaml")
        .skip(1)
        .map(|rest| rest.split("```").next().unwrap_or("").to_string())
        .collect()
}

/// The text of one `join: { … }` record, from the key to its closing brace.
///
/// Written across several lines in §7.3 because the record has five keys and a
/// line an author cannot read is not a specification. So this accumulates lines
/// rather than matching one.
fn join_records(yaml: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut current: Option<String> = None;
    for line in yaml.lines() {
        if current.is_none() && line.trim_start().starts_with("join:") {
            current = Some(String::new());
        }
        if let Some(buf) = current.as_mut() {
            buf.push_str(line);
            buf.push('\n');
            if line.contains('}') {
                out.push(current.take().expect("just borrowed"));
            }
        }
    }
    out
}

/// The keys written on a `join:` record — `group`, `waits-for`, and whatever
/// qualifies them.
fn join_keys(record: &str) -> Vec<String> {
    let mut out = Vec::new();
    for chunk in record.split(&[',', '{', '\n'][..]) {
        let chunk = chunk.split('#').next().unwrap_or(chunk);
        let chunk = chunk.trim().trim_start_matches("join:").trim();
        if let Some((key, _)) = chunk.split_once(':') {
            let key = key.trim();
            if !key.is_empty() && key.chars().all(|c| c.is_ascii_lowercase() || c == '-') {
                out.push(key.to_string());
            }
        }
    }
    out
}

/// The ways of waiting a `join:` record offers, read off its `waits-for:` value.
///
/// The value is a `a | b | c` alternation that wraps, so this takes everything
/// between `waits-for:` and the next key and splits it.
fn waits_in(record: &str) -> BTreeSet<String> {
    let after = record
        .split_once("waits-for:")
        .unwrap_or_else(|| panic!("a join record with no `waits-for:` — this one says:\n{record}"))
        .1;
    // Stop at the next key of the record. `<duration>` and the like never
    // appear before it, so the first `<lowercase-word>:` is the boundary.
    let mut value = String::new();
    for line in after.lines() {
        let line = line.split('#').next().unwrap_or(line);
        let stripped = line.trim();
        let is_next_key = stripped
            .split_once(':')
            .is_some_and(|(k, _)| !k.is_empty() && k.chars().all(|c| c.is_ascii_lowercase() || c == '-'));
        if is_next_key && !value.is_empty() {
            break;
        }
        value.push_str(line);
        value.push(' ');
    }
    value
        .split('|')
        .map(|w| w.trim().trim_end_matches([',', '}']).trim().to_string())
        .filter(|w| !w.is_empty())
        .collect()
}

/// The `choices:` of one field of one group in `spec/schema.yaml`.
///
/// A line scan, for the reason `eve_inventory.rs` gives for its own: the job is
/// to say which word is missing from which document, and the schema's shape —
/// `groups:` ▸ two-space group ▸ `fields:` ▸ six-space field — makes that a
/// short function. A parser would make the failure message harder to write.
fn schema_choices(group: &str, field: &str) -> BTreeSet<String> {
    let text = schema();
    let block = field_block(&text, group, field);
    let after = block
        .split_once("choices:")
        .unwrap_or_else(|| panic!("`{group}.{field}` in spec/schema.yaml has no `choices:`"))
        .1;
    // `choices: [a, b]` or `choices:` on its own line with the list under it,
    // possibly wrapped — both are in the file today.
    let list = after
        .split_once('[')
        .and_then(|(_, rest)| rest.split_once(']'))
        .map(|(inner, _)| inner.to_string())
        .unwrap_or_else(|| panic!("`{group}.{field}` writes its choices in a shape this reads as a list"));
    list.split(',')
        .map(|w| w.split('#').next().unwrap_or(w).trim().to_string())
        .filter(|w| !w.is_empty())
        .collect()
}

/// Whether a line opens something at exactly `indent` spaces — the schema's
/// only structure. Two spaces is a group, six is a field of one.
fn opens_at(line: &str, indent: usize) -> Option<&str> {
    let key = line.strip_prefix(&" ".repeat(indent))?;
    if key.starts_with(' ') {
        return None;
    }
    let key = key.trim_end().strip_suffix(':')?;
    (!key.is_empty() && key.chars().all(|c| c.is_ascii_lowercase() || c == '-')).then_some(key)
}

/// The lines of one group of `spec/schema.yaml`, up to the next group.
///
/// Line-scanned rather than split on `"\n  "`, because that prefix also matches
/// the start of every field four levels down and quietly returns nothing.
fn group_body(text: &str, group: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut inside = false;
    for line in text.lines() {
        match opens_at(line, 2) {
            Some(name) if name == group => {
                inside = true;
                continue;
            }
            Some(_) if inside => break,
            _ => {}
        }
        if inside {
            out.push(line.to_string());
        }
    }
    assert!(!out.is_empty(), "spec/schema.yaml has no `{group}` group");
    out
}

/// The lines of one field of one group, up to the next field.
fn field_block(text: &str, group: &str, field: &str) -> String {
    let mut out = Vec::new();
    let mut inside = false;
    for line in group_body(text, group) {
        match opens_at(&line, 6) {
            Some(name) if name == field => {
                inside = true;
                continue;
            }
            Some(_) if inside => break,
            _ => {}
        }
        if inside {
            out.push(line);
        }
    }
    assert!(
        !out.is_empty(),
        "`{group}` in spec/schema.yaml has no `{field}` field"
    );
    out.join("\n")
}

/// Every field name of one group of `spec/schema.yaml`, in file order.
fn schema_fields(group: &str) -> Vec<String> {
    group_body(&schema(), group)
        .iter()
        .filter_map(|line| opens_at(line, 6).map(str::to_string))
        .collect()
}

/// The one `join:` record §7.3 defines, which is the edge's normative form.
fn the_edge_join() -> String {
    yaml_blocks(&section("7.3"))
        .iter()
        .flat_map(|b| join_records(b))
        .next()
        .expect("§7.3's edge block must still define a `join:` record — that is what the section is")
}

#[test]
fn the_graph_and_the_author_have_exactly_one_set_of_words_for_how_a_team_waits() {
    // The guarantee this file exists for, stated as set equality in both
    // directions. Containment either way is not enough: a word only the schema
    // has is a wait the graph cannot express, and a word only §7.3 has is a
    // wait no author can ask for — and the second is how `first-ok` and
    // `all-settled` came to exist at all.
    let authored = schema_choices("teamwork", "waits-for");
    let emitted = waits_in(&the_edge_join());

    let only_authored: Vec<&String> = authored.difference(&emitted).collect();
    let only_emitted: Vec<&String> = emitted.difference(&authored).collect();

    assert!(
        only_authored.is_empty(),
        "spec/schema.yaml lets an author write {only_authored:?} under `teamwork.waits-for`, and \
         §7.3's `join:` has no such wait. Either add the spelling to §7.3, or take the choice out \
         of the schema — an author must not be able to write a line the graph cannot carry."
    );
    assert!(
        only_emitted.is_empty(),
        "§7.3's `join:` offers {only_emitted:?}, and `teamwork.waits-for` in spec/schema.yaml has \
         no such choice. A way of waiting nobody can author is a second vocabulary, which is what \
         `all-settled` and `first-ok` were."
    );
    assert_eq!(
        authored, emitted,
        "the two documents must name the same five ways to wait"
    );
    assert_eq!(
        authored.len(),
        5,
        "there are five ways to wait (§7.16 JOIN-2) and the schema now offers {}",
        authored.len()
    );
}

#[test]
fn the_join_on_an_edge_names_its_settings_with_the_authors_own_field_names() {
    // The wait is not the only word that was going to be spelled twice.
    // `enough-is`, `gives-up-after`, `if-someone-fails` and `asks` all qualify a
    // wait, and R5's `quorum(k)` had already smuggled one of them into a
    // *value*. So every key on the emitted record other than the group name has
    // to be a field an author actually writes.
    let record = the_edge_join();
    let authored = schema_fields("teamwork");
    assert!(
        authored.contains(&"waits-for".to_string()),
        "spec/schema.yaml's `teamwork` group no longer has `waits-for`; this test is reading the \
         wrong group"
    );

    for key in join_keys(&record) {
        if key == "group" {
            // The one key with no authored counterpart, and it has a reason:
            // grouping is a graph concept (§7.3, the AutoGen `activation_group`
            // argument), not something a `teamwork.yaml` can express.
            continue;
        }
        assert!(
            authored.contains(&key),
            "§7.3's `join:` carries `{key}:`, and `teamwork` in spec/schema.yaml has no such \
             field — it has: {}. Either the author can write it, or the graph should not carry it.",
            authored.join(", ")
        );
    }
}

#[test]
fn an_unset_wait_means_wait_for_everyone_in_the_graph_as_it_does_for_the_author() {
    // The half of the defect that was worse than the spelling. Two vocabularies
    // a reader can translate; two DEFAULTS silently produce different runs from
    // the same file, and the four authored lines of the worked example were
    // exactly such a file.
    let body = section("7.3");
    assert!(
        body.contains("Unset `waits-for` defaults to\n`everyone`")
            || body.contains("Unset `waits-for` defaults to `everyone`"),
        "§7.3 must say what an unset wait means, and say `everyone` — the schema's default and \
         Eve's behaviour"
    );
    assert!(
        !body.contains("defaults to `any`"),
        "§7.3 still defaults the join to `any` while `teamwork:` defaults to `everyone`. That is \
         the same four authored lines meaning 'wait for both' in the harness and 'carry on at the \
         first reply' in the graph."
    );
}

#[test]
fn all_settled_is_gone_as_a_way_of_waiting_because_a_failure_rule_already_has_a_name() {
    // `all-settled` was `everyone` plus `carry-on` wearing one word. Keeping
    // both is the construct overlap this document's own style rule forbids, and
    // it is checkable: the failure rule has to be on the record, and the fused
    // spelling has to be off it.
    let record = the_edge_join();
    assert!(
        !record.contains("all-settled"),
        "§7.3's `join:` still offers `all-settled`, which is `everyone` plus \
         `if-someone-fails: carry-on`:\n{record}"
    );
    assert!(
        join_keys(&record).contains(&"if-someone-fails".to_string()),
        "`all-settled` may only be deleted if the failure rule it fused is separately writable on \
         the same record. §7.3's `join:` has no `if-someone-fails:`:\n{record}"
    );
    for gone in ["first-ok", "quorum("] {
        assert!(
            !record.contains(gone),
            "§7.3's `join:` still spells a wait as {gone:?}, which no author can type:\n{record}"
        );
    }
}

#[test]
fn every_line_of_the_teamwork_block_has_a_stated_home_in_the_desugared_graph() {
    // The other half of gap (1): §7.7 used to emit bare member edges, so five
    // of the eight authored lines were dropped on the floor by the desugaring.
    // JOIN-10 is the table that fixed it, and a table with a row missing is the
    // same defect in a nicer format.
    let body = section("7.7");
    let table = body
        .split("JOIN-10")
        .nth(1)
        .expect("§7.7 must carry JOIN-10, the table saying where each authored line goes");

    for field in schema_fields("teamwork") {
        assert!(
            table.contains(&format!("| `{field}` |")),
            "JOIN-10 has no row for `teamwork.{field}`, so the desugaring drops it. Every line an \
             author writes has to land somewhere in the emitted graph, or writing it does nothing."
        );
    }
}

#[test]
fn the_desugared_member_edges_carry_the_join_the_author_wrote() {
    // The concrete failure gap (1) described: `{from: policy-checker, to:
    // supervisor}` with no `join:` at all, so the emitted graph fell back to
    // §7.3's default and the worked example ran two different ways depending on
    // which document you believed.
    let body = section("7.7");
    let emitted = yaml_blocks(&body)
        .into_iter()
        .find(|b| b.contains("entrypoint: supervisor"))
        .expect("§7.7 must still show the graph `team:` desugars to");

    let records = join_records(&emitted);
    assert_eq!(
        records.len(),
        2,
        "the two-member team desugars to two member edges and each carries the join — found {} \
         `join:` records in the emitted graph",
        records.len()
    );

    let authored = schema_choices("teamwork", "waits-for");
    for record in &records {
        // VAL-4: every member edge into the group carries the same policy, so
        // each one is checked rather than the first.
        let waits = waits_in(record);
        assert_eq!(
            waits.len(),
            1,
            "an emitted edge must commit to ONE wait, not offer the menu: {record}"
        );
        let wait = waits.iter().next().expect("just counted");
        assert!(
            authored.contains(wait),
            "§7.7 emits `waits-for: {wait}`, which is not a choice `teamwork.waits-for` offers: {}",
            authored.iter().cloned().collect::<Vec<_>>().join(", ")
        );
    }
    assert_eq!(
        records[0].replace(char::is_whitespace, ""),
        records[1].replace(char::is_whitespace, ""),
        "VAL-4 says all member edges into one group agree; §7.7's own example must show that"
    );
}

#[test]
fn no_normative_form_in_the_document_still_spells_a_wait_the_old_way() {
    // A rename that leaves four call sites reading the old word has not removed
    // the second vocabulary, it has moved it. The historical accounts of what
    // R5 wrote are deliberately left alone — a document that cannot say what it
    // used to say cannot explain why it changed — so this checks the places a
    // reader takes as *current*: every YAML form in the document, and §7.6's
    // validation rules, which named `mode: all` twice.
    let text = arch();
    for (n, block) in yaml_blocks(&text).into_iter().enumerate() {
        for record in join_records(&block) {
            for gone in ["mode:", "all-settled", "first-ok", "quorum("] {
                assert!(
                    !record.contains(gone),
                    "YAML block {n} of the architecture draft writes a join with {gone:?}. The \
                     authored words are the only words: {record}"
                );
            }
        }
    }

    let rules = section("7.6");
    assert!(
        rules.contains("`waits-for: everyone`"),
        "§7.6's VAL rules must name the wait in the author's words"
    );
    assert!(
        !rules.contains("`mode: all`"),
        "§7.6 still validates `mode: all`, a spelling §7.3 no longer defines — so the rule names a \
         field that does not exist, which is what VAL-2 was already caught doing once"
    );
}

#[test]
fn the_two_documents_point_at_each_other_and_at_this_test() {
    // The lesson `eve_inventory.rs` records: two documents that only point one
    // way decay in the direction nobody reads. §7.3 has to say that the schema
    // is where the words come from, and both have to name the test that holds
    // them, or the next person to change one has no way of knowing.
    let body = section("7.3");
    assert!(
        body.contains("spec/schema.yaml"),
        "§7.3 must name the file its five spellings are taken from"
    );
    assert!(
        body.contains("crates/pact-cli/tests/one_name_for_how_a_team_waits.rs"),
        "§7.3 must name the test that keeps it in step with the schema"
    );
    assert!(
        section("7.16").contains("one_name_for_how_a_team_waits.rs"),
        "§7.16's gap (1) records the closure, so it must name what makes the closure falsifiable"
    );
}
