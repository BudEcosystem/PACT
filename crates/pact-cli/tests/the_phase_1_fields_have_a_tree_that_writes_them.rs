//! Every field the Phase 1 work added is written by one fixture tree, and that
//! tree is read through the real binary.
//!
//! `teamwork.may-start:` and its two bounds were written by no tree in this
//! repository: every test of them built the document in another language and
//! handed it to a reader, so a loader that stopped carrying one of them would
//! have been noticed by nothing. Fixture:
//! `tests/trees/a-desk-that-writes-every-phase-1-field/`.

use std::process::Command;

fn tree() -> String {
    format!(
        "{}/../../tests/trees/a-desk-that-writes-every-phase-1-field",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn pact(args: &[&str]) -> (Option<i32>, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .output()
        .expect("runs");
    (
        out.status.code(),
        format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    )
}

#[test]
fn the_tree_is_clean_and_every_field_reaches_the_document() {
    let (code, said) = pact(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(code, Some(0), "{said}");

    let (code, shown) = pact(&["show", &tree()]);
    assert_eq!(code, Some(0), "{shown}");
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("`pact show` prints JSON");
    let desk = &doc["agents"]["desk"];
    // Each as the author wrote it, at the place a runtime reads it from.
    assert_eq!(desk["run-inputs"]["shop"], "text");
    assert_eq!(desk["checks-at-most"], 3);
    assert_eq!(desk["checked-by"][0]["must-contain"][0], "refund");
    assert_eq!(
        desk["checked-by"][1]["must-call-before"]["first"],
        "orders/look-up"
    );
    assert_eq!(desk["limits"]["starts-at-most"], 4);
    assert_eq!(desk["limits"]["nests-at-most"], 1);
    assert_eq!(
        desk["teamwork"]["may-start"],
        serde_json::json!(["catalogue", "narrowed-new"])
    );
    let hands_back = &doc["tools"]["orders"]["actions"]["look-up"]["answers-with"];
    assert_eq!(hands_back["status"], "one of delivered, in-transit, lost");
    assert_eq!(hands_back["total"], "money");
    assert!(
        desk["instructions"]
            .as_str()
            .unwrap()
            .contains("{{run-inputs.shop}}"),
        "a hole is carried unfilled: its value arrives with a run"
    );
}

/// The negative half: the tree is not clean by accident. Each bound `may-start:`
/// needs is one the checker asks for, at this tree's own line.
#[test]
fn may_start_without_either_of_its_bounds_is_refused() {
    for bound in ["starts-at-most: 4\n", "nests-at-most: 1\n"] {
        let dst = std::env::temp_dir().join(format!(
            "pact-phase1-{}-{}",
            &bound[..5],
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dst);
        copy_dir(std::path::Path::new(&tree()), &dst);
        let limits = dst.join("agents/desk/limits.yaml");
        let text = std::fs::read_to_string(&limits).unwrap();
        assert!(text.contains(bound), "fixture drifted: {bound:?}");
        std::fs::write(&limits, text.replace(bound, "")).unwrap();
        let (code, said) = pact(&["check", dst.to_str().unwrap()]);
        assert_eq!(
            code,
            Some(1),
            "`may-start:` loaded without `{}`:\n{said}",
            bound.trim()
        );
        assert!(said.contains(bound.split(':').next().unwrap()), "{said}");
        let _ = std::fs::remove_dir_all(&dst);
    }
}

fn copy_dir(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}
