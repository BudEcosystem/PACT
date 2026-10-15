//! `run_time_composition_stays_bounded`, the loader's half (02W §8, R16 as 02P
//! §8.1 narrows it). Three things `pact check` refuses before anything runs:
//!
//! 1. `may-start:` without both `limits.starts-at-most:` and
//!    `limits.nests-at-most:` (WF-33, first case: `teamwork.rs`);
//! 2. a `run-code` stage whose `may-use:` reaches an agent, a workflow or a
//!    program that can wait (WF-33, second case: `code.rs`), since code cannot
//!    stop and wait: a teammate whose own loop asks, one whose memory a person
//!    reviews, one its caller asks about when it fails, a workflow that calls an
//!    agent, an agent over A2A, a program whose fuel asks a person;
//! 3. `run-code` without `fuel:` (A3: `needed-when:` on `stage.does`).
//!
//! And the lines beside them that are never read: `fuel:` on a stage that runs
//! no code. The run-time half (a narrowed agent naming what its starter lacks is
//! refused; a write behind *Ask before* is never made from code) is the
//! runtime's, and is tested there.
//!
//! Driven against the shipped `an-agent-that-uses-a-workflow` tree, given a
//! locked room, a teammate and a loop whose one stage runs code.

use std::path::{Path, PathBuf};
use std::process::Command;

const FUEL: &str = "    fuel:\n      runs-for-at-most: 30s\n      memory-at-most: 256m\n      when-it-runs-out: stop-and-say-so\n";

/// The shipped tree, with `files` written over it (`""` deletes the file).
fn tree(name: &str, files: &[(&str, &str)]) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/trees/an-agent-that-uses-a-workflow");
    let dst = std::env::temp_dir().join(format!("pact-composition-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    let base: [(&str, &str); 4] = [
        (
            "resources/room.yaml",
            "resource-kind: sandbox\ndescription: A room.\nengines:\n  - python\n",
        ),
        (
            "agents/desk.yaml",
            "description: Answers questions about an order.\ninstructions: Find the order.\n\
             loop: compute\nuses:\n  - order-status\nteam:\n  adder: Adds figures up.\n",
        ),
        (
            "agents/adder.yaml",
            "description: Adds figures up.\ninstructions: Add them.\n",
        ),
        ("loops/compute.yaml", ""),
    ];
    for (file, text) in base.iter().chain(files) {
        let at = dst.join(file);
        if text.is_empty() {
            let _ = std::fs::remove_file(&at);
            continue;
        }
        std::fs::create_dir_all(at.parent().unwrap()).unwrap();
        std::fs::write(at, text).unwrap();
    }
    dst
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for entry in std::fs::read_dir(src).unwrap() {
        let entry = entry.unwrap();
        let to = dst.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &to);
        } else {
            std::fs::copy(entry.path(), to).unwrap();
        }
    }
}

/// A loop whose one stage runs code that may use `names`, with `fuel` beside it.
fn code_loop(names: &[&str], fuel: &str) -> String {
    let listed: String = names.iter().map(|n| format!("      - {n}\n")).collect();
    format!(
        "description: Work it out in code.\nstarts-at: work\nsteps:\n  work:\n    does: run-code\n    \
         may-use:\n{listed}{fuel}    then:\n      answered: done\n"
    )
}

fn check(tree: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(tree)
        .output()
        .unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

#[test]
fn code_that_calls_only_what_never_waits_and_states_its_fuel_loads() {
    let loop_ = code_loop(&["adder", "order-status", "orders"], FUEL);
    let (ok, said) = check(&tree("clean", &[("loops/compute.yaml", &loop_)]));
    assert!(ok, "{said}");
}

#[test]
fn run_code_without_fuel_is_refused() {
    let loop_ = code_loop(&["adder"], "");
    let (ok, said) = check(&tree("no-fuel", &[("loops/compute.yaml", &loop_)]));
    assert!(!ok, "{said}");
    assert!(said.contains("schema/missing-companion"), "{said}");
    assert!(
        said.contains("how long and how much its code may run"),
        "{said}"
    );
}

#[test]
fn code_that_may_call_a_teammate_who_can_wait_is_refused() {
    let loop_ = code_loop(&["adder"], FUEL);
    let waits = "description: Adds figures up.\ninstructions: Add them.\nlimits:\n  \
                 steps-at-most: 3\n  when-it-runs-out: ask-a-person\n  asks: keep-going\n";
    let question = "description: Keep going?\nsays: Shall it keep going?\nanswer:\n  \
                    approved: yes or no\nasked-of: [leads]\nanswer-within: 1h\n\
                    if-nobody-answers: stop-and-say-so\n";
    let (ok, said) = check(&tree(
        "teammate",
        &[
            ("loops/compute.yaml", &loop_),
            ("agents/adder.yaml", waits),
            ("questions/keep-going.yaml", question),
        ],
    ));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/code-calls-what-can-wait"), "{said}");
    assert!(said.contains("'adder' can stop and wait"), "{said}");
    assert!(
        said.contains("keep-going"),
        "the why names what it waits for: {said}"
    );
}

#[test]
fn code_that_may_call_a_workflow_that_can_wait_is_refused() {
    let loop_ = code_loop(&["order-status"], FUEL);
    let flow = "description: Looks up an order and says where it is.\npublished-as: [tool]\n\
                accepts:\n  order-number: text\nanswers-with:\n  status: text\nstarts-at: look\n\
                steps:\n  look:\n    does: call\n    call: adder\n    then:\n      answered: reply\n  \
                reply:\n    does: answer\n    bind:\n      status: steps.look.answer\n";
    let (ok, said) = check(&tree(
        "workflow",
        &[
            ("loops/compute.yaml", &loop_),
            ("workflows/order-status.yaml", flow),
        ],
    ));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/code-calls-what-can-wait"), "{said}");
    assert!(said.contains("its stage 'look' calls 'adder'"), "{said}");
}

#[test]
fn code_that_may_call_a_program_that_asks_for_more_fuel_is_refused() {
    let loop_ = code_loop(&["calc"], FUEL);
    let desk = "description: Answers questions about an order.\ninstructions: Find the order.\n\
                loop: compute\nuses:\n  - order-status\n  - calc\nteam:\n  adder: Adds figures up.\n";
    let calc = "description: Spins in the room.\nconnect: room\nactions:\n  spin:\n    \
                description: Spin a while.\n    program: spin\n    reads-only: yes\n";
    let spin = "description: Spins.\nengine: python\ndeterminism: pure\nanswers-with:\n  \
                content: text\nfuel:\n  runs-for-at-most: 1s\n  when-it-runs-out: ask-a-person\n";
    let (ok, said) = check(&tree(
        "program",
        &[
            ("loops/compute.yaml", &loop_),
            ("agents/desk.yaml", desk),
            ("tools/calc.yaml", calc),
            ("programs/spin/program.yaml", spin),
            ("programs/spin/body/main.py", "while True:\n    pass\n"),
        ],
    ));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/code-calls-what-can-wait"), "{said}");
    assert!(
        said.contains("its program 'spin' asks a person when it runs out of fuel"),
        "{said}"
    );
}

#[test]
fn code_that_may_call_a_teammate_whose_failure_its_caller_asks_about_is_refused() {
    let loop_ = code_loop(&["adder"], FUEL);
    let desk = "description: Answers questions about an order.\ninstructions: Find the order.\n\
                loop: compute\nuses:\n  - order-status\nteam:\n  adder: Adds figures up.\n\
                teamwork:\n  if-someone-fails: ask-a-person\n  asks: carry-on\n";
    let question = "description: Carry on?\nsays: Shall it carry on without them?\nanswer:\n  \
                    approved: yes or no\nasked-of: [leads]\nanswer-within: 1h\n\
                    if-nobody-answers: stop-and-say-so\n";
    let (ok, said) = check(&tree(
        "caller",
        &[
            ("loops/compute.yaml", &loop_),
            ("agents/desk.yaml", desk),
            ("questions/carry-on.yaml", question),
        ],
    ));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/code-calls-what-can-wait"), "{said}");
    assert!(said.contains("if-someone-fails: ask-a-person"), "{said}");
}

#[test]
fn code_that_may_call_an_agent_over_a2a_is_refused() {
    let loop_ = code_loop(&["bookings"], FUEL);
    let desk = "description: Answers questions about an order.\ninstructions: Find the order.\n\
                loop: compute\nuses:\n  - order-status\n  - bookings\nteam:\n  adder: Adds figures up.\n";
    let tool = "description: The booking agent.\nconnect: booker\nactions:\n  book-slot:\n    \
                description: Book one slot.\n    takes:\n      request: text\n";
    let (ok, said) = check(&tree(
        "a2a",
        &[
            ("loops/compute.yaml", &loop_),
            ("agents/desk.yaml", desk),
            ("tools/bookings.yaml", tool),
            (
                "resources/booker.yaml",
                "resource-kind: a2a-agent\nendpoint: host/booker\ndescription: Books slots.\n",
            ),
        ],
    ));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/code-calls-what-can-wait"), "{said}");
    assert!(said.contains("reached over A2A"), "{said}");
}

#[test]
fn code_that_may_call_a_teammate_whose_memory_is_reviewed_is_refused() {
    let loop_ = code_loop(&["adder"], FUEL);
    let adder = "description: Adds figures up.\ninstructions: Add them.\nremembers:\n  colour:\n    \
                 description: a colour\n    lasts: forever\n    starts-as: green\n";
    let (ok, said) = check(&tree(
        "reviewed",
        &[
            ("loops/compute.yaml", &loop_),
            ("agents/adder.yaml", adder),
            ("learning.yaml", "enabled: propose-only\n"),
        ],
    ));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/code-calls-what-can-wait"), "{said}");
    assert!(said.contains("held for a person's review"), "{said}");
}

#[test]
fn code_that_may_bring_agents_in_through_a_teammate_is_refused() {
    let loop_ = code_loop(&["adder"], FUEL);
    let starts = "description: Adds figures up.\ninstructions: Add them.\nteamwork:\n  \
                  may-start: [catalogue]\nlimits:\n  starts-at-most: 20\n  nests-at-most: 2\n  \
                  when-it-runs-out: stop-and-say-so\n";
    let (ok, said) = check(&tree(
        "starts",
        &[
            ("loops/compute.yaml", &loop_),
            ("agents/adder.yaml", starts),
        ],
    ));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/code-calls-what-can-wait"), "{said}");
    assert!(said.contains("may-start"), "{said}");
}

#[test]
fn may_start_without_its_two_ceilings_is_refused() {
    let starts = "description: Answers questions about an order.\ninstructions: Find the order.\n\
                  uses:\n  - order-status\nteamwork:\n  may-start: [catalogue]\n";
    let (ok, said) = check(&tree("unbounded", &[("agents/desk.yaml", starts)]));
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/may-start-without-its-bounds"),
        "{said}"
    );
}

#[test]
fn fuel_beside_a_stage_that_runs_no_code_is_never_read() {
    let loop_ = format!(
        "description: Think.\nstarts-at: think\nsteps:\n  think:\n    does: think\n{FUEL}    \
         then:\n      answered: done\n"
    );
    let (ok, said) = check(&tree("think", &[("loops/compute.yaml", &loop_)]));
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-line-this-stage-never-reads"),
        "{said}"
    );
    assert!(said.contains("writes `fuel:`"), "{said}");
}
