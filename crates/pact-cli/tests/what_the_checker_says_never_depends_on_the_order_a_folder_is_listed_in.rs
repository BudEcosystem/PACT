//! What `pact check` reports about a tree is a property of the tree, never of
//! the order the filesystem happens to list a folder in.
//!
//! `read_dir` gives entries in the order the disk keeps them, and that order
//! changes from one machine to the next (ext4 lists by a hash seeded per
//! filesystem; tmpfs by when each entry was made). When two entries in one
//! folder become the same setting, the one read second is the one
//! `loader/duplicate-field` reports, so before the loader sorted its reads a
//! tree with `agents/keeper/` and a named pipe `agents/keeper.yaml` answered
//! `loader/not-a-regular-file` here and `loader/duplicate-field` on GitHub's
//! runner, and the gate went red on one and green on the other.
//!
//! The tree below has 32 such pairs, `Pick07.yaml` beside `pick07.yaml`, made
//! in a scrambled order (neither sorted nor reverse-sorted, and the upper-case
//! name first for half of them). Read in name order, `Pick..` comes before
//! `pick..` every time, so every report names the lower-case file. A loader
//! that took the disk's order instead would match that on all 32 pairs about
//! once in four billion times.
//!
//! # Mutation
//!
//! In `pact_loader::entries_by_name`, delete the `sort_by_key` line.
//! **`a_clash_is_always_reported_at_the_name_that_sorts_second` fails**.

use std::process::Command;

const PAIRS: usize = 32;

struct Ws(std::path::PathBuf);

impl Drop for Ws {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn write(root: &std::path::Path, rel: &str, body: &str) {
    let p = root.join(rel);
    std::fs::create_dir_all(p.parent().unwrap()).unwrap();
    std::fs::write(p, body).unwrap();
}

#[test]
fn a_clash_is_always_reported_at_the_name_that_sorts_second() {
    let base = std::env::temp_dir().join(format!("pact-cli-listing-order-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    let ws = Ws(base);
    write(
        &ws.0,
        "workspace.yaml",
        "name: desk-ws\ndescription: A workspace.\n",
    );
    write(
        &ws.0,
        "agents/keeper/agent.yaml",
        "name: Keeper\ndescription: Keeps things.\ninstructions: Keep things.\n",
    );
    let tool = "description: Picks one.\n";
    // 13 is coprime with 32, so this visits every pair once, out of order.
    for step in 0..PAIRS {
        let i = (step * 13) % PAIRS;
        let (upper, lower) = (
            format!("tools/Pick{i:02}.yaml"),
            format!("tools/pick{i:02}.yaml"),
        );
        if i.is_multiple_of(2) {
            write(&ws.0, &lower, tool);
            write(&ws.0, &upper, tool);
        } else {
            write(&ws.0, &upper, tool);
            write(&ws.0, &lower, tool);
        }
    }

    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", ws.0.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );

    for i in 0..PAIRS {
        assert!(
            said.contains(&format!(
                "'Pick{i:02}.yaml' and 'pick{i:02}.yaml' would both become"
            )),
            "pair {i}: the clash must be told in name order, whatever order the disk \
             listed the two files in.\n{said}"
        );
        assert!(
            !said.contains(&format!("'pick{i:02}.yaml' and 'Pick{i:02}.yaml'")),
            "pair {i} was reported the other way round, so the loader read the \
             folder in the disk's order.\n{said}"
        );
    }
    assert_eq!(
        said.matches("rule: loader/duplicate-field").count(),
        PAIRS,
        "one report per pair, no more.\n{said}"
    );
}
