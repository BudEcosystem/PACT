//! The PACT language (`docs/99-THE-PACT-LANGUAGE.md` §4): a `.pact` file is a
//! second way of WRITING a workspace, and never a second workspace.
//!
//! What is held here is the round trip, in both directions, on every workspace
//! this repository ships: `pact write` prints a folder as one file, and reading
//! that file gives back the document the folder gave. A keyword the language
//! cannot print fails this test on the day it is added to the specification —
//! which is the whole of how the two ways of writing are kept from drifting.

use std::path::{Path, PathBuf};
use std::process::Command;

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn pact(args: &[&str]) -> (i32, String, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .output()
        .unwrap();
    (
        out.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&out.stdout).to_string(),
        String::from_utf8_lossy(&out.stderr).to_string(),
    )
}

fn shown(path: &Path) -> serde_json::Value {
    let (code, out, err) = pact(&["show", path.to_str().unwrap()]);
    assert_eq!(code, 0, "{} does not load:\n{err}", path.display());
    serde_json::from_str(&out).unwrap()
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("pact-lang-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// Every workspace under `examples/` that is written as a folder.
fn folders(dir: &Path, out: &mut Vec<PathBuf>) {
    if dir.join("workspace.yaml").exists() {
        out.push(dir.to_path_buf());
        return;
    }
    let mut entries: Vec<_> = std::fs::read_dir(dir).unwrap().flatten().collect();
    entries.sort_by_key(std::fs::DirEntry::path);
    for e in entries {
        if e.file_type().unwrap().is_dir() {
            folders(&e.path(), out);
        }
    }
}

/// The files a document refers to rather than holds: they stay files.
fn kept(node: &serde_json::Value, out: &mut Vec<String>) {
    match node {
        serde_json::Value::Object(o) => {
            if let Some(f) = o.get("$file").and_then(|f| f.as_str()) {
                out.push(f.to_string());
            } else if let Some(root) = o.get("$payload").and_then(|f| f.as_str()) {
                for f in o["files"].as_array().into_iter().flatten() {
                    out.push(format!("{}/{}", root.trim_end_matches('/'), f["$file"].as_str().unwrap()));
                }
            } else {
                o.values().for_each(|v| kept(v, out));
            }
        }
        serde_json::Value::Array(a) => a.iter().for_each(|v| kept(v, out)),
        _ => {}
    }
}

#[test]
fn every_shipped_workspace_reads_back_from_what_pact_write_prints() {
    let mut all = Vec::new();
    folders(&repo().join("examples"), &mut all);
    assert!(all.len() >= 27, "found only {} workspaces under examples/", all.len());
    for workspace in all {
        let want = shown(&workspace);
        let (code, text, err) = pact(&["write", workspace.to_str().unwrap()]);
        assert_eq!(code, 0, "`pact write {}` failed:\n{err}", workspace.display());

        // The text, at the top of a folder that still holds what stays a file.
        let dir = scratch("round").join(workspace.file_name().unwrap());
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("workspace.pact"), &text).unwrap();
        let mut files = Vec::new();
        kept(&want, &mut files);
        assert_eq!(
            err.contains("stay files"),
            !files.is_empty(),
            "`pact write` says what it left as files exactly when it left some: {err}"
        );
        for file in files {
            let to = dir.join(&file);
            std::fs::create_dir_all(to.parent().unwrap()).unwrap();
            std::fs::copy(workspace.join(&file), to).unwrap();
        }
        assert_eq!(
            shown(&dir),
            want,
            "{} reads differently as a PACT-language file:\n{text}",
            workspace.display()
        );
    }
}

#[test]
fn the_same_workspace_written_two_ways() {
    for (written, folder) in [
        ("examples/language/finance-first", "examples/kernel/finance-first"),
        ("examples/language/staff-desk", "examples/answers-from-documents"),
    ] {
        assert_eq!(
            shown(&repo().join(written)),
            shown(&repo().join(folder)),
            "{written} and {folder} are meant to be one workspace"
        );
    }
    // And the file on its own is the workspace the folder holding it is.
    assert_eq!(
        shown(&repo().join("examples/language/finance-first/finance-first.pact")),
        shown(&repo().join("examples/language/finance-first")),
    );
}

#[test]
fn every_language_example_loads_with_no_warnings() {
    for example in ["hello", "finance-first", "staff-desk"] {
        let dir = repo().join("examples/language").join(example);
        let (code, out, err) = pact(&["check", dir.to_str().unwrap(), "--deny-warnings"]);
        assert_eq!(code, 0, "{example}:\n{out}{err}");
    }
}

#[test]
fn pact_build_writes_the_folder_the_file_stands_for() {
    let file = repo().join("examples/language/finance-first/finance-first.pact");
    let to = scratch("build").join("out");
    let (code, out, err) = pact(&["build", file.to_str().unwrap(), "--to", to.to_str().unwrap()]);
    assert_eq!(code, 0, "{out}{err}");
    assert!(to.join("workspace.yaml").exists());
    assert!(to.join("agents/support/agent.yaml").exists());
    assert!(to.join("agents/support/instructions.md").exists());
    assert!(to.join("reactions/wrap-up.yaml").exists());
    assert!(to.join("topics/finance.yaml").exists());
    assert_eq!(shown(&to), shown(&file));

    // It writes over nothing.
    let (code, _, err) = pact(&["build", file.to_str().unwrap(), "--to", to.to_str().unwrap()]);
    assert_eq!(code, 2, "{err}");
    assert!(err.contains("rule: cli/build-into-something-there"), "{err}");
    // And it is told what to build, and where.
    let (code, _, err) = pact(&["build", file.to_str().unwrap()]);
    assert_eq!(code, 2);
    assert!(err.contains("rule: cli/build-needs-a-folder"), "{err}");
    let (code, _, err) = pact(&["build", to.to_str().unwrap(), "--to", "/nowhere"]);
    assert_eq!(code, 2);
    assert!(err.contains("rule: cli/build-needs-a-pact-file"), "{err}");
}

#[test]
fn a_mistake_is_told_on_the_line_it_was_written_on() {
    let dir = scratch("mistakes");
    let file = dir.join("team.pact");
    std::fs::write(
        &file,
        "workspace \"T\"\n\nagnt desk\n  description: x\n\nagent desk\n  description: Helps.\n  \
         instructions: Help.\n  use zendesk\n  takes message\n  when the moon is full\n    \
         remind it: howl\ndescription: stray\n\tindented: with a tab\n",
    )
    .unwrap();
    let (code, out, _) = pact(&["check", file.to_str().unwrap()]);
    assert_eq!(code, 1, "{out}");
    for (rule, line) in [
        ("lang/no-such-block", "team.pact:3:1"),
        ("lang/not-a-line", "team.pact:9:3"),
        ("lang/not-a-line", "team.pact:10:9"),
        ("lang/not-a-signal", "team.pact:11:8"),
        ("lang/a-setting-in-no-block", "team.pact:13:1"),
        ("lang/a-tab-in-the-margin", "team.pact:14:1"),
    ] {
        assert!(out.contains(&format!("rule: {rule}")), "no {rule} in:\n{out}");
        assert!(out.contains(line), "nothing at {line} in:\n{out}");
    }
    assert!(out.contains("Did you mean `agent`?"), "{out}");
    assert!(out.contains("Did you mean a line starting `uses`?"), "{out}");
}

#[test]
fn the_checker_s_own_rules_point_into_the_pact_file() {
    // Nothing about the language: a tool that is not there is refused by the
    // rule that refuses it in a folder, at the word in the `.pact` file.
    let dir = scratch("names");
    let file = dir.join("team.pact");
    std::fs::write(
        &file,
        "workspace \"T\"\n\nagent desk\n  description: Helps.\n  instructions: Help.\n  uses zendesk\n",
    )
    .unwrap();
    let (code, out, _) = pact(&["check", file.to_str().unwrap()]);
    assert_eq!(code, 1);
    assert!(out.contains("rule: schema/no-such-name"), "{out}");
    assert!(out.contains("team.pact:6:8"), "{out}");
}

#[test]
fn a_pact_file_adds_to_its_folder_and_says_nothing_twice() {
    let dir = scratch("beside");
    std::fs::create_dir_all(dir.join("agents/helper")).unwrap();
    std::fs::write(
        dir.join("agents/helper/agent.yaml"),
        "description: Helps.\ninstructions: Help.\n",
    )
    .unwrap();
    std::fs::write(
        dir.join("team.pact"),
        "workspace \"T\"\n\nagent desk\n  description: Answers.\n  instructions: Answer.\n  \
         asks helper: Helps with the hard ones.\n",
    )
    .unwrap();
    let (code, out, err) = pact(&["check", dir.to_str().unwrap(), "--deny-warnings"]);
    assert_eq!(code, 0, "{out}{err}");
    let doc = shown(&dir);
    assert!(doc["agents"]["desk"].is_object() && doc["agents"]["helper"].is_object(), "{doc}");

    // The same agent in both places is refused, as a field set in two files is.
    std::fs::write(
        dir.join("more.pact"),
        "agent helper\n  description: A second helper.\n  instructions: Help.\n",
    )
    .unwrap();
    let (code, out, _) = pact(&["check", dir.to_str().unwrap()]);
    assert_eq!(code, 1, "{out}");
    assert!(out.contains("rule: loader/ambiguous-field"), "{out}");

    // And a `.pact` file is a whole workspace's worth: it sits at the top.
    std::fs::remove_file(dir.join("more.pact")).unwrap();
    std::fs::write(dir.join("agents/extra.pact"), "agent extra\n  description: x\n").unwrap();
    let (code, out, _) = pact(&["check", dir.to_str().unwrap()]);
    assert_eq!(code, 1, "{out}");
    assert!(out.contains("rule: loader/a-pact-file-below-the-top"), "{out}");
}

#[test]
fn every_collection_has_a_header_word() {
    let text = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let schema = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml")).unwrap();
    let fields = schema.get("groups").unwrap().get("workspace").unwrap().get("fields").unwrap();
    for (name, field) in fields.as_map().unwrap() {
        let ty = field.node.get("type").and_then(pact_doc::Node::as_str).unwrap_or_default();
        if ty.starts_with("map of ") {
            assert!(
                pact_lang::word_for(name).is_some(),
                "`{name}:` is a collection of the workspace, and `pact_lang::COLLECTIONS` has no \
                 header word for it — add one, or it can only be written as a setting"
            );
        } else if ty.starts_with("group:") {
            assert!(
                pact_lang::SINGLES.contains(&name.as_str()),
                "`{name}:` is one document of the workspace, and `pact_lang::SINGLES` does not \
                 list it"
            );
        }
    }
    for (word, collection) in pact_lang::COLLECTIONS {
        assert!(
            fields.get(collection).is_some(),
            "`{word}` is a header word for `{collection}:`, which the workspace does not have"
        );
    }
}

#[test]
fn discover_finds_a_workspace_written_as_a_pact_file() {
    let (code, out, err) = pact(&["discover", repo().join("examples/language").to_str().unwrap()]);
    assert_eq!(code, 0, "{err}");
    let found: serde_json::Value = serde_json::from_str(&out).unwrap();
    let text = found.to_string();
    for name in ["Hello", "Finance first", "Staff desk"] {
        assert!(text.contains(name), "`pact discover` did not find {name}: {text}");
    }
}
