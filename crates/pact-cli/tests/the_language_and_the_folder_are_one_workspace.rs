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
    for example in ["hello", "finance-first", "staff-desk", "help-centre"] {
        let dir = repo().join("examples/language").join(example);
        let (code, out, err) = pact(&["check", dir.to_str().unwrap(), "--deny-warnings"]);
        assert_eq!(code, 0, "{example}:\n{out}{err}");
    }
}

/// The blocks of `text` that start with `word`, each with its name.
fn blocks<'a>(text: &'a str, word: &str) -> Vec<(&'a str, Vec<&'a str>)> {
    let mut out: Vec<(&str, Vec<&str>)> = Vec::new();
    let mut inside = false;
    for line in text.lines() {
        if !line.starts_with(' ') && !line.is_empty() {
            inside = line.split(' ').next() == Some(word);
            if inside {
                out.push((line.split(' ').nth(1).unwrap_or_default(), Vec::new()));
            }
        } else if inside && let Some(block) = out.last_mut() {
            block.1.push(line);
        }
    }
    out
}

#[test]
fn every_shipped_workflow_and_loop_is_written_in_the_order_it_runs() {
    // `docs/99` §4.6: a workflow's stages are written as statements, one after
    // another, where an order of lines can say how they are wired. Every one
    // this repository ships can be — so `steps:` and `starts-at:` appear in
    // none of them, and the round trip above holds that what is written
    // instead reads back as the same stages.
    let mut all = Vec::new();
    folders(&repo().join("examples"), &mut all);
    let mut seen = 0;
    for workspace in all {
        let (code, text, err) = pact(&["write", workspace.to_str().unwrap()]);
        assert_eq!(code, 0, "{err}");
        for word in ["workflow", "loop"] {
            for (name, lines) in blocks(&text, word) {
                // A loop that only says which ready-made shape it starts from
                // has no stages of its own to write.
                if !lines.iter().any(|l| l.contains(" = ") || l.trim_start().starts_with("answer")) {
                    assert!(
                        !lines.iter().any(|l| l.trim_start().starts_with("steps:")),
                        "the {word} '{name}' in {} is written as settings:\n{text}",
                        workspace.display()
                    );
                    continue;
                }
                seen += 1;
                for line in lines {
                    assert!(
                        !matches!(line.trim_start(), l if l.starts_with("steps:") || l.starts_with("starts-at:")),
                        "the {word} '{name}' in {} is written as settings:\n{text}",
                        workspace.display()
                    );
                }
            }
        }
    }
    assert!(seen >= 11, "found only {seen} workflows and loops written as statements");
}

#[test]
fn a_workspace_in_several_files_is_the_one_file_pact_write_prints() {
    // `examples/language/help-centre` is four `.pact` files: figures with
    // names, a pattern and two desks made from it, two workflows with one
    // calling the other, a reaction, and how it learns.
    let folder = repo().join("examples/language/help-centre");
    let files: Vec<_> = std::fs::read_dir(&folder)
        .unwrap()
        .flatten()
        .filter(|e| e.path().extension().is_some_and(|x| x == "pact"))
        .collect();
    assert_eq!(files.len(), 4);
    let want = shown(&folder);
    for (collection, at_least) in [("agents", 4), ("workflows", 2), ("tools", 1), ("reactions", 1)] {
        let have = want[collection].as_object().map_or(0, serde_json::Map::len);
        assert!(have >= at_least, "{collection}: {have}");
    }
    assert_eq!(want["learning"]["enabled"], "propose-only");

    let (code, text, err) = pact(&["write", folder.to_str().unwrap()]);
    assert_eq!(code, 0, "{err}");
    // What the four files said in sentences, the one file says in sentences.
    for line in [
        "let large-refund = 200 USD",
        "  based on desk with domain: billing, cap: 0.10 USD",
        "  where = decide",
        "    if billing",
        "  every = for each item in input.messages",
        "    one = call route with message: item.text, channel: item.channel",
        "  done-all = answer with replies: every.reply",
    ] {
        assert!(text.lines().any(|l| l == line), "no `{line}` in:\n{text}");
    }
    let one = scratch("one-file").join("help-centre.pact");
    std::fs::write(&one, &text).unwrap();
    assert_eq!(shown(&one), want, "{text}");

    // And the folder of YAML it stands for is the same workspace again.
    let built = scratch("one-file-built").join("help-centre");
    let (code, out, err) = pact(&["build", one.to_str().unwrap(), "--to", built.to_str().unwrap()]);
    assert_eq!(code, 0, "{out}{err}");
    assert_eq!(shown(&built), want);
}

#[test]
fn a_name_no_step_has_is_told_where_it_was_read() {
    let dir = scratch("no-such-step");
    let file = dir.join("hello.pact");
    std::fs::write(
        &file,
        "workspace \"Hello\"\n\n\
         agent greeter\n  description: Says hello.\n  takes message: text\n  gives reply: text\n  \
         instructions: Greet whoever writes to you.\n\n\
         workflow hello\n  description: Ask one agent and hand back what it said.\n  \
         takes message: text\n  gives reply: text\n  \
         greet = call greeter with message: input.message\n  \
         answer with reply: nobody.reply\n",
    )
    .unwrap();
    let (code, out, err) = pact(&["check", file.to_str().unwrap()]);
    let said = format!("{out}{err}");
    assert_eq!(code, 1, "{said}");
    // The rule is the one a folder of YAML gets, and it points at the name as
    // it was written — `nobody.reply`, on the line of the statement.
    assert!(said.contains("rule: loader/a-binding-to-nothing"), "{said}");
    assert!(said.contains("hello.pact:14:22"), "{said}");
    assert!(said.contains("no stage called 'nobody'"), "{said}");
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
