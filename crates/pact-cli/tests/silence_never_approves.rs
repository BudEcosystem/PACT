//! Silence never approves (02W §3 WF-20, §8; WAIT-4, R13, R50).
//!
//! A wait a person answers may not, by its silence, reach a stage whose call a
//! person must allow first, or a write its own yes leads to, before another
//! wait. A wait only the clock and events answer has no gate, so its one exit
//! may lead anywhere.
//!
//! Three things are held here, over the five worked trees of 02W §5
//! (`tests/trees/workflows-*`):
//!
//! - the first diagnostic 02W §3 prints, from its mutated copy of §5.2;
//! - a silent exit that reaches a call needing a person's yes;
//! - the mutation sweep: every `nobody-answered:` in the fixtures pointed at
//!   every stage beside it. WF-20 refuses exactly the mutations a small,
//!   separate reading of the tree (`pact show`'s document, walked here) says
//!   reach a gated stage or a write an answer reaches, and accepts the rest.

use serde_json::Value;
use std::collections::{BTreeSet, VecDeque};
use std::path::{Path, PathBuf};
use std::process::Command;

const RULE: &str = "loader/silence-reaches-a-gated-step";
const TREES: [&str; 5] = [
    "workflows-16-trial-booking",
    "workflows-48-invoices",
    "workflows-69-reflexion",
    "workflows-79-supervisor",
    "workflows-60-interconnection",
];

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree(name: &str) -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/trees")).join(name)
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

fn scratch(label: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-silence-{label}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    dst
}

fn check(root: &Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

fn edited(name: &str, label: &str, file: &str, from: &str, to: &str) -> PathBuf {
    let dst = scratch(label);
    copy(&tree(name), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(text.contains(from), "fixture drifted: {from:?} not in {file}");
    std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    dst
}

const OWNER_APPROVES: &str = "  owner-approves:\n    does: ask-someone\n    asks: budget-owner-approves\n    then: { answered: post, declined: tell-sender, nobody-answered: tell-clerk }\n";

#[test]
fn the_printed_example_prints_as_the_design_shows_it() {
    // 02W §3's first print, from #48 with silence sent where a yes goes. The
    // design writes "posting is what a yes would have done"; the loader names
    // the stage as the author wrote it.
    let root = edited(
        "workflows-48-invoices",
        "printed",
        "workflows/one-invoice.yaml",
        OWNER_APPROVES,
        "  owner-approves:\n    does: ask-someone\n    asks: budget-owner-approves\n    then:\n      answered: post\n      declined: tell-sender\n      nobody-answered: post\n",
    );
    let (ok, text) = check(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "error: 'post' can be reached when nobody answered 'owner-approves', and 'post' is \
             what a yes would have done — so silence would act as a yes."
        ),
        "{text}"
    );
    assert!(text.contains("|       nobody-answered: post\n"), "{text}");
    assert!(
        text.contains("|       ^^^^^^^^^^^^^^^\n"),
        "the caret is under `nobody-answered`:\n{text}"
    );
    assert!(
        text.contains(
            "fix: Send this exit somewhere that asks again or only tells someone — \
             `nobody-answered: tell-clerk` — or to `stop-and-say-so`."
        ),
        "{text}"
    );
    assert!(text.contains(&format!("rule: {RULE}")), "{text}");
    assert_eq!(text.matches(RULE).count(), 1, "{text}");
}

#[test]
fn silence_may_not_reach_a_call_a_person_must_allow() {
    // Telling the clerk is fine, until telling the clerk itself needs a yes.
    let root = edited(
        "workflows-48-invoices",
        "guarded",
        "tools/teams.yaml",
        "    description: Post one message in a channel, its wording filled in.\n",
        "    description: Post one message in a channel, its wording filled in.\n    needs-a-person: yes\n",
    );
    let (ok, text) = check(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'tell-clerk' can be reached when nobody answered 'owner-approves', and it calls \
             `teams/post-message`, which says `needs-a-person: yes` — so silence would stand \
             where a yes must."
        ),
        "{text}"
    );
    // Three waits send their silence there; each is told at its own exit.
    assert_eq!(text.matches(&format!("rule: {RULE}")).count(), 3, "{text}");
}

#[test]
fn silence_may_go_to_another_wait_or_to_a_stage_only_a_no_reaches() {
    for to in ["controller-approves", "tell-sender", "stop-and-say-so", "done"] {
        let root = edited(
            "workflows-48-invoices",
            &format!("fine-{to}"),
            "workflows/one-invoice.yaml",
            OWNER_APPROVES,
            &OWNER_APPROVES.replace("nobody-answered: tell-clerk", &format!("nobody-answered: {to}")),
        );
        let (_, text) = check(&root);
        let _ = std::fs::remove_dir_all(&root);
        assert!(!text.contains(RULE), "{to}:\n{text}");
    }
}

// ──────────────────────────────────────────────────────────── the sweep

/// The document `pact show` prints for a tree.
fn shown(root: &Path) -> Value {
    let out = pact()
        .args(["show", root.to_str().unwrap()])
        .output()
        .expect("runs");
    serde_json::from_slice(&out.stdout).expect("pact show prints JSON")
}

/// A separate, small reading of what WF-20 promises, over the shown document.
struct Oracle<'a> {
    doc: &'a Value,
    workflow: &'a Value,
}

const ENDS: [&str; 2] = ["done", "stop-and-say-so"];

impl<'a> Oracle<'a> {
    fn steps(&self) -> &'a serde_json::Map<String, Value> {
        self.workflow["steps"].as_object().expect("steps")
    }

    fn person_answers(&self, stage: &Value) -> bool {
        if stage["does"] != "ask-someone" {
            return false;
        }
        let asks = stage["asks"].as_str().unwrap_or("");
        let q = self.workflow["questions"]
            .get(asks)
            .or_else(|| self.doc["questions"].get(asks));
        let ports = self.doc["ports"].as_object();
        q.and_then(|q| q["asked-of"].as_array())
            .is_some_and(|who| {
                who.iter().filter_map(Value::as_str).any(|w| {
                    w != "the-clock" && !ports.is_some_and(|p| p.contains_key(w))
                })
            })
    }

    fn next(stage: &Value) -> Vec<String> {
        let mut out = Vec::new();
        for key in ["then", "chooses-between"] {
            for (_, v) in stage[key].as_object().into_iter().flatten() {
                match v {
                    Value::String(s) => out.push(s.clone()),
                    Value::Object(heard) => out.extend(
                        heard.values().filter_map(Value::as_str).map(str::to_string),
                    ),
                    _ => {}
                }
            }
        }
        out.retain(|s| !ENDS.contains(&s.as_str()));
        out
    }

    fn action(&self, call: &str) -> Option<&'a Value> {
        let (tool, action) = call.split_once('/')?;
        self.doc["tools"].get(tool)?["actions"].get(action)
    }

    fn writes(&self, stage: &Value, depth: usize) -> bool {
        if depth > 8 {
            return false;
        }
        if let Some(body) = stage["steps"].as_object()
            && body.values().any(|s| self.writes(s, depth + 1))
        {
            return true;
        }
        let Some(call) = stage["call"].as_str() else {
            return false;
        };
        if let Some(a) = self.action(call) {
            return a["reads-only"] != Value::Bool(true) && a["reads-only"] != "yes";
        }
        self.doc["workflows"]
            .get(call)
            .and_then(|w| w["steps"].as_object())
            .is_some_and(|steps| steps.values().any(|s| self.writes(s, depth + 1)))
    }

    fn guarded(&self, stage: &Value) -> bool {
        let needs = |s: &Value| {
            s["call"]
                .as_str()
                .and_then(|c| self.action(c))
                .is_some_and(|a| a["needs-a-person"] == Value::Bool(true) || a["needs-a-person"] == "yes")
        };
        needs(stage)
            || stage["steps"]
                .as_object()
                .is_some_and(|b| b.values().any(needs))
    }

    /// What `answered:` of `wait` leads to; past a later wait a person
    /// answers, only that wait's yes.
    fn yes(&self, wait: &Value) -> BTreeSet<String> {
        let mut out = BTreeSet::new();
        let mut queue: VecDeque<String> =
            wait["then"]["answered"].as_str().map(str::to_string).into_iter().collect();
        while let Some(here) = queue.pop_front() {
            let Some(stage) = self.steps().get(&here) else {
                continue;
            };
            if !out.insert(here) {
                continue;
            }
            if self.person_answers(stage) {
                queue.extend(stage["then"]["answered"].as_str().map(str::to_string));
            } else {
                queue.extend(Self::next(stage));
            }
        }
        out
    }

    /// Whether silence sent to `to` reaches what only a yes may.
    fn refused(&self, wait: &Value, to: &str) -> bool {
        if !self.person_answers(wait) || ENDS.contains(&to) {
            return false;
        }
        let yes = self.yes(wait);
        let mut seen = BTreeSet::from([to.to_string()]);
        let mut queue = VecDeque::from([to.to_string()]);
        while let Some(here) = queue.pop_front() {
            let Some(stage) = self.steps().get(&here) else {
                continue;
            };
            if stage["does"] == "ask-someone" {
                continue;
            }
            if self.guarded(stage) || (yes.contains(&here) && self.writes(stage, 0)) {
                return true;
            }
            for n in Self::next(stage) {
                if seen.insert(n.clone()) {
                    queue.push_back(n);
                }
            }
        }
        false
    }
}

/// Every `nobody-answered: <stage>` in one workflow file: where its value is,
/// and the top-level stage it belongs to.
fn exits(text: &str) -> Vec<(usize, usize, String)> {
    let mut out = Vec::new();
    let mut stage = String::new();
    let mut offset = 0;
    for line in text.split_inclusive('\n') {
        let bare = line.trim_end();
        if let Some(name) = bare.strip_prefix("  ").and_then(|r| r.strip_suffix(':'))
            && !name.starts_with(' ')
            && !name.contains(' ')
        {
            stage = name.to_string();
        }
        if let Some(at) = line.find("nobody-answered: ") {
            let start = at + "nobody-answered: ".len();
            let len = line[start..]
                .find(|c: char| !(c.is_ascii_alphanumeric() || c == '-'))
                .unwrap_or(line.len() - start);
            out.push((offset + start, len, stage.clone()));
        }
        offset += line.len();
    }
    out
}

#[test]
fn every_silent_exit_pointed_at_every_stage_is_refused_exactly_when_it_reaches_a_gate() {
    let (mut refused, mut accepted, mut ungated_waits) = (0, 0, 0);
    for name in TREES {
        let src = tree(name);
        let doc = shown(&src);
        for entry in std::fs::read_dir(src.join("workflows")).unwrap().flatten() {
            let file = entry.path();
            let flow = file.file_stem().unwrap().to_str().unwrap().to_string();
            let text = std::fs::read_to_string(&file).unwrap();
            let workflow = &doc["workflows"][&flow];
            let oracle = Oracle {
                doc: &doc,
                workflow,
            };
            for (at, len, wait) in exits(&text) {
                let wait_node = &workflow["steps"][&wait];
                assert_eq!(wait_node["does"], "ask-someone", "{name}/{flow}: {wait}");
                if !oracle.person_answers(wait_node) {
                    ungated_waits += 1;
                }
                let mut targets: Vec<String> = oracle.steps().keys().cloned().collect();
                targets.extend(ENDS.iter().map(|s| s.to_string()));
                for to in targets {
                    let mutated = format!("{}{}{}", &text[..at], to, &text[at + len..]);
                    let root = scratch(&format!("sweep-{flow}-{wait}-{to}"));
                    copy(&src, &root);
                    std::fs::write(root.join("workflows").join(file.file_name().unwrap()), &mutated)
                        .unwrap();
                    let (_, said) = check(&root);
                    let _ = std::fs::remove_dir_all(&root);
                    let expected = oracle.refused(wait_node, &to);
                    let told = said.contains(&format!("rule: {RULE}"));
                    assert_eq!(
                        told, expected,
                        "{name}/{flow}: `nobody-answered: {to}` on '{wait}'\n{said}"
                    );
                    if expected {
                        refused += 1;
                    } else {
                        accepted += 1;
                    }
                }
            }
        }
    }
    // The sweep holds both directions, over gated waits and waits only the
    // clock and events answer.
    assert!(refused >= 10, "only {refused} refusals");
    assert!(accepted >= 50, "only {accepted} acceptances");
    assert!(ungated_waits >= 4, "only {ungated_waits} waits with no gate");
}
