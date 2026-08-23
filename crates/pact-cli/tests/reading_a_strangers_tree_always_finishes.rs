//! **Reading somebody else's tree terminates, and costs what the tree costs.**
//!
//! R5's premise is that `pact check` never executes an author's code, so reading
//! a workspace a stranger sent you is safe. Safe is two promises, not one: the
//! reading must not RUN anything, and it must FINISH. The second half had two
//! holes, one of them opened by P3.
//!
//! **A `.pactignore` that is not a file.** `Ignore::load` called
//! `read_to_string` on `<dir>/.pactignore` with no check of what that name is,
//! at every directory from the root down. The loader knows this hazard and
//! guards it everywhere else — a FIFO, socket or device found by the payload
//! walk raises `loader/not-a-regular-file`, and a symlink raises
//! `loader/symlink-skipped` — but `.pactignore` is opened before either walk can
//! see it. Measured: `mkfifo .pactignore` in a workspace made `check`, `show`,
//! `waits`, `discover` and `card` all block for ever with no output at all. And
//! `.pactignore -> /etc/passwd` loaded cleanly, with that file's lines becoming
//! ignore patterns and its text quoted back in a diagnostic.
//!
//! It matters most for `pact discover`, which is specified to be run over trees
//! its operator did not write. Refusing to run somebody's code and then hanging
//! for ever on their file is the same guarantee broken from the other side.
//!
//! **A payload file with no ceiling.** Before payload digests, the payload walk
//! only asked the filesystem for each entry's size — cost proportional to the
//! NUMBER of files. Fingerprinting reads every byte, and nothing bounded it:
//! `MAX_LOAD_TEXT` is charged from `load_file`, and neither fingerprint call
//! passes through there. A tree can state a size independently of what it
//! occupies, so a 48 KiB directory could cost a reviewer minutes. Measured on
//! `examples/answers-from-documents` with one sparse file planted in it: the
//! release build went from 0.006 s to 1.05 s at 512 MB and 8.65 s at 4 GiB, with
//! the tree 48 KiB on disk throughout.
//!
//! The repair keeps the honest answer the field already documents. A file too
//! big to describe is carried by name and size with NO digest, and a warning
//! names it — rather than a guess, or a wait: "a made-up digest would be worse
//! than none, because the whole value of the field is that it can be compared."

#![cfg(unix)]

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn seed(name: &str) -> std::path::PathBuf {
    let src = format!("{}/../../tests/trees/a-desk-with-a-program", env!("CARGO_MANIFEST_DIR"));
    let dst = std::env::temp_dir().join(format!("pact-finishes-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&src), &dst);
    dst
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

/// Run `pact` and refuse to wait for ever.
///
/// A hung child is the failure under test, so the test may not hang either. The
/// wait is generous — this is a correctness test, not a benchmark — and the
/// failure it reports is the one that matters: the process never came back.
fn within(seconds: u64, args: &[&str]) -> (Option<i32>, String) {
    let mut child = pact()
        .args(args)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .expect("starts");
    let waited = std::time::Instant::now();
    loop {
        match child.try_wait().expect("waits") {
            Some(_) => break,
            None if waited.elapsed().as_secs() >= seconds => {
                let _ = child.kill();
                let _ = child.wait();
                panic!(
                    "`pact {}` did not finish in {seconds}s — reading a tree has to end",
                    args.join(" ")
                );
            }
            None => std::thread::sleep(std::time::Duration::from_millis(25)),
        }
    }
    let out = child.wait_with_output().expect("collects");
    (
        out.status.code(),
        format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    )
}

fn mkfifo(at: &std::path::Path) {
    let ok = Command::new("mkfifo").arg(at).status().expect("mkfifo runs");
    assert!(ok.success(), "could not make a pipe at {}", at.display());
}

/// The hang, on every verb that reads a tree.
#[test]
fn a_pipe_named_pactignore_does_not_stop_the_reader_for_ever() {
    let dst = seed("fifo");
    mkfifo(&dst.join(".pactignore"));
    let at = dst.to_string_lossy().into_owned();
    for verb in [
        vec!["check", &at],
        vec!["show", &at],
        vec!["waits", &at],
        vec!["discover", &at],
    ] {
        let (code, said) = within(20, &verb);
        assert!(code.is_some(), "`pact {}` came back with no code:\n{said}", verb.join(" "));
    }
    let _ = std::fs::remove_dir_all(&dst);
}

/// And it says what it did rather than pretending the file was empty — once.
///
/// The ignore list is INHERITED, so every directory from the root down asks for
/// the same file and the same skipped one is found again each time. The comment
/// that shipped with this said `Diagnostics` folds identical entries; it does
/// not. Measured on a six-directory tree: NINE copies of one sentence about one
/// file, which is one thing to fix rendered as a wall.
#[test]
fn a_pactignore_that_is_not_a_file_is_said_out_loud_once() {
    let dst = seed("fifo-said");
    mkfifo(&dst.join(".pactignore"));
    let (_, said) = within(20, &["check", &dst.to_string_lossy()]);
    assert!(
        said.contains("not-a-regular-file") || said.contains("pactignore"),
        "an author has to be told which file was skipped and why:\n{said}"
    );
    assert_eq!(
        said.matches("loader/not-a-regular-file").count(),
        1,
        "one file, one mistake, one sentence:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// A `.pactignore` that is a shortcut out of the workspace is not followed.
///
/// Nothing above the tree being loaded may reach into it — that rule is already
/// written on `Ignore::inherited`, and a symlink walked round it.
#[test]
fn a_pactignore_that_points_outside_the_tree_is_not_read() {
    let dst = seed("link");
    let outside = dst.join("..").join(format!("pact-outside-{}", std::process::id()));
    std::fs::write(&outside, "programs\n").unwrap();
    std::os::unix::fs::symlink(&outside, dst.join(".pactignore")).unwrap();
    let (code, said) = within(20, &["check", &dst.to_string_lossy()]);
    assert_eq!(code, Some(0), "{said}");
    assert!(
        !said.contains("ignored-on-purpose"),
        "a file outside the tree must not become this tree's ignore list:\n{said}"
    );
    let _ = std::fs::remove_file(&outside);
    let _ = std::fs::remove_dir_all(&dst);
}

/// A shortcut to a real file INSIDE the tree is followed, because it reaches
/// nothing the tree does not already hold.
///
/// The rule `Ignore::inherited` states is that nothing ABOVE the tree may reach
/// into it, and the repair that stopped `.pactignore -> /etc/passwd` overshot:
/// it refused every link, so a workspace whose `.pactignore` is a shortcut to a
/// shared file one folder along inside the same tree silently stopped ignoring
/// anything. And the sentence it printed — "a shortcut to something that is not
/// a file" — was untrue of a link pointing straight at a file.
#[test]
fn a_pactignore_that_points_at_a_real_file_in_the_tree_is_read() {
    let dst = seed("link-inside");
    std::fs::write(dst.join("shared-ignore.txt"), "check-window.wasm\n").unwrap();
    std::os::unix::fs::symlink("shared-ignore.txt", dst.join(".pactignore")).unwrap();
    let (code, said) = within(20, &["check", &dst.to_string_lossy()]);
    assert!(code.is_some(), "{said}");
    assert!(
        !said.contains("not-a-regular-file"),
        "a link to a file in this tree points at a file:\n{said}"
    );
    assert!(
        said.contains("ignored-on-purpose"),
        "and the lines in it are this tree's ignore rules:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// A payload file too big to describe is described anyway — by name and size.
#[test]
fn a_payload_file_with_no_ceiling_does_not_become_the_readers_problem() {
    let dst = seed("huge");
    let body = dst.join("programs/check-window/body/huge.wasm");
    let f = std::fs::File::create(&body).unwrap();
    // Stated, not occupied: 8 GiB of length on a file that costs nothing on
    // disk. This is exactly the gap between what a tree SAYS it holds and what
    // it cost the author to send.
    f.set_len(8 * 1024 * 1024 * 1024).unwrap();
    drop(f);
    let at = dst.to_string_lossy().into_owned();
    let (code, said) = within(60, &["check", &at]);
    assert!(code.is_some(), "{said}");
    assert!(
        said.contains("huge.wasm"),
        "name the file that could not be fingerprinted:\n{said}"
    );

    // And it is still carried — by name and size, with no fingerprint. An empty
    // digest is not written out at all, which is the same honest answer the
    // field documents: "a made-up digest would be worse than none, because the
    // whole value of the field is that it can be compared."
    let (_, shown) = within(60, &["show", &at]);
    let entry = shown
        .find("huge.wasm")
        .unwrap_or_else(|| panic!("the file is still carried, by name and size:\n{shown}"));
    let rest = &shown[entry..];
    let ends = rest.find('}').expect("the entry closes");
    assert!(rest[..ends].contains("8589934592"), "with its size:\n{}", &rest[..ends]);
    assert!(
        !rest[..ends].contains("digest"),
        "and no fingerprint, rather than a guess:\n{}",
        &rest[..ends]
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// The positive control: an ordinary body is still fingerprinted.
#[test]
fn an_ordinary_payload_file_still_carries_its_fingerprint() {
    let dst = seed("ordinary");
    let (_, shown) = within(20, &["show", &dst.to_string_lossy()]);
    assert!(
        shown.contains("check-window.wasm"),
        "the shipped body is carried:\n{shown}"
    );
    assert!(
        !shown.contains("\"digest\": \"\""),
        "nothing in this tree is too big to describe:\n{shown}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}
