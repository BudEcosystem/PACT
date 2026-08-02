//! A self file supplies its folder's own settings — and nothing it does not
//! hold.
//!
//! The Expansion Rule says *a directory is a field; a field may be a directory*,
//! and a **self file** (`agent.yaml`, `_index.yaml`, `SKILL.md`) is where that
//! directory's own fields are written. What it contributes when it is not a set
//! of settings used to be decided by one `_ =>` arm that folded *anything else*
//! into the body field, including a document holding nothing at all.
//!
//! That is how `# TODO` in `agents/fraud-checker/agent.yaml` came to be reported
//! as *"'content' is not something an agent can have — fix: Remove it"*: the
//! loader had invented a `content` field, and then the schema complained about
//! its own invention while the author looked at a two-word file that plainly
//! does not contain the word.
//!
//! These write real files and load them with the real [`Loader`], so what is
//! asserted is what an author's tree actually becomes. Nothing is built in
//! memory; every case starts as text on disk.

use camino::Utf8PathBuf;
use pact_diag::Diagnostics;
use pact_doc::Node;
use pact_loader::Loader;
use std::fs;
use std::sync::atomic::{AtomicU32, Ordering};

static COUNTER: AtomicU32 = AtomicU32::new(0);

struct Tree(Utf8PathBuf);

impl Tree {
    /// A folder whose self file is `self_body`, with one ordinary sibling
    /// setting beside it. The sibling is there in every case so that "the self
    /// file contributed nothing" can be told apart from "the folder failed to
    /// load".
    fn with_self_file(name: &str, file: &str, self_body: &str) -> Self {
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
            .join(format!("pact-selffile-{name}-{}-{n}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(base.join("thing")).unwrap();
        fs::write(base.join("thing").join(file), self_body).unwrap();
        fs::write(base.join("thing/instructions.md"), "Be brief.\n").unwrap();
        Self(base)
    }

    fn load(&self) -> (Node, Diagnostics) {
        let mut d = Diagnostics::new();
        let n = Loader::new(self.0.clone()).load(&self.0, &mut d).expect("the folder loads");
        d.sort();
        (n, d)
    }
}

impl Drop for Tree {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn a_self_file_holding_only_a_comment_adds_no_setting_of_its_own() {
    let t = Tree::with_self_file("comment", "thing.yaml", "# TODO\n");
    let (root, d) = t.load();
    let thing = root.get("thing").expect("the folder is still a field");

    assert!(
        thing.get("content").is_none(),
        "a file with no document in it has no body, so there is nothing to name it: {}",
        thing.to_json()
    );
    assert_eq!(
        thing.as_map().expect("a set of settings").len(),
        1,
        "only the sibling file contributed: {}",
        thing.to_json()
    );
    assert_eq!(thing.get("instructions").unwrap().as_str().unwrap().trim(), "Be brief.");
    assert!(!d.has_errors(), "an unfinished file is not a broken one:\n{}", d.render());
}

#[test]
fn a_self_file_with_nothing_in_it_at_all_adds_no_setting_of_its_own() {
    // Zero bytes is the state every file passes through on its way to existing.
    let t = Tree::with_self_file("empty", "thing.yaml", "");
    let (root, d) = t.load();
    let thing = root.get("thing").expect("the folder is still a field");
    assert!(thing.get("content").is_none(), "nothing in, nothing out: {}", thing.to_json());
    assert!(thing.get("instructions").is_some(), "and the siblings still load");
    assert!(!d.has_errors(), "{}", d.render());
}

#[test]
fn a_self_file_written_as_prose_and_left_blank_adds_no_setting_of_its_own() {
    // The two tests above are the same file in `.yaml`. In `.md` it took the
    // OTHER branch and the invented setting came back, because prose has no
    // "absent" form: an empty markdown file is not nothing, it is a body with
    // no words in it. Measured before this: `thing.md` of zero bytes loaded as
    // `{"content": "", "instructions": "Be brief.\n"}`, and end to end that
    // printed `'content' is not something an agent can have — fix: Remove it`
    // against a file with nothing in it to remove.
    //
    // Both spellings of blank are here because they are one state to the
    // author: "New File" gives zero bytes, and pressing return a few times
    // before saving gives the other.
    for (name, body) in [("emptyprose", ""), ("blankprose", "   \n\n")] {
        let t = Tree::with_self_file(name, "thing.md", body);
        let (root, d) = t.load();
        let thing = root.get("thing").expect("the folder is still a field");
        assert!(
            thing.get("content").is_none(),
            "a markdown file the author has not written yet has no body either: {}",
            thing.to_json()
        );
        assert_eq!(
            thing.as_map().expect("a set of settings").len(),
            1,
            "only the sibling file contributed: {}",
            thing.to_json()
        );
        assert!(thing.get("instructions").is_some(), "and the siblings still load");
        assert!(!d.has_errors(), "an unfinished file is not a broken one:\n{}", d.render());
    }
}

#[test]
fn a_self_file_written_as_prose_becomes_the_folders_body() {
    // The branch the empty case was wrongly sharing, and the reason it cannot
    // just be deleted: `skills/<name>/SKILL.md` with no settings at the top IS
    // the procedure. The prose has to arrive, whole.
    let t = Tree::with_self_file("prose", "thing.md", "Check the order date, then decide.\n");
    let (root, d) = t.load();
    let body = root
        .get("thing")
        .and_then(|n| n.get("content"))
        .and_then(|n| n.as_str())
        .unwrap_or_else(|| panic!("prose must still become the body: {}", root.to_json()));
    assert_eq!(body.trim(), "Check the order date, then decide.");
    assert!(!d.has_errors(), "{}", d.render());
}

#[test]
fn a_self_file_that_is_neither_settings_nor_prose_is_named_rather_than_renamed() {
    // T7 — no silent loss. The author wrote something, so they are owed a
    // message about what they wrote. Folding it under a setting name they never
    // typed was a message about something else entirely.
    let t = Tree::with_self_file("list", "thing.yaml", "- one\n- two\n");
    let (root, d) = t.load();

    let e = d
        .items()
        .iter()
        .find(|x| x.rule == "loader/self-file-not-settings")
        .unwrap_or_else(|| panic!("this cannot pass silently:\n{}", d.render()));
    assert!(e.message.contains("thing.yaml"), "name the file: {}", e.message);
    assert!(e.message.contains("a list"), "and say what it is instead: {}", e.message);
    assert!(e.fix.contains("description:"), "O7.3: give a line to type: {}", e.fix);
    assert!(
        !e.message.contains("Value") && !e.message.contains("Seq"),
        "D13: no type names in anything an author reads: {}",
        e.message
    );

    let thing = root.get("thing").expect("the folder still loads");
    assert!(
        thing.get("content").is_none(),
        "and no setting is invented to carry it: {}",
        thing.to_json()
    );
    assert!(thing.get("instructions").is_some(), "the siblings are untouched");
}

#[test]
fn a_self_file_that_is_settings_still_supplies_them() {
    // The ordinary case, kept beside the others so a change to the branch has
    // to keep passing it.
    let t = Tree::with_self_file("map", "thing.yaml", "name: thing\ndescription: Does a thing.\n");
    let (root, d) = t.load();
    let thing = root.get("thing").unwrap();
    assert_eq!(thing.get("name").unwrap().as_str(), Some("thing"));
    assert_eq!(thing.get("description").unwrap().as_str(), Some("Does a thing."));
    assert!(thing.get("instructions").is_some());
    assert!(!d.has_errors(), "{}", d.render());
}
