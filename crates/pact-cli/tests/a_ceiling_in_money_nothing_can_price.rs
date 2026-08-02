//! A spend cap in one currency, a bill counted in another, and `pact check`
//! saying nothing.
//!
//! Held from `pact check` rather than from the loader, for the reason
//! `shares_are_checked_where_the_author_is` gives: a Rust caller is not where
//! the author is. Every case below starts from the SHIPPED worked example and
//! changes one line of it, so what is under test is the author's line reaching
//! the check — not an object a test built in Rust and then asked about itself.
//!
//! Measured before `pact_loader::currency` existed: copy `examples/refund-desk`,
//! change `agents/refund-desk/limits.yaml` from `cost-per-request-under: 0.05
//! USD` to `cost-per-request-under: 500 JPY`, and this command printed
//! *"OK — … loaded cleanly (492 settings)."* and exited 0. The ceiling then ran
//! against a meter priced from `models/catalog.yaml`, which charges in USD, and
//! the sentence the author got back at 501 was *"(501 of 500 USD)"* — a currency
//! they never wrote, after a comparison that had already treated 500 JPY and
//! 500 USD as the same money.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply `edits` as (file, from, to), return the root.
fn edited(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-currency-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(text.contains(from), "fixture drifted: {from:?} not found in {file}");
        std::fs::write(&p, text.replace(from, to)).unwrap();
    }
    dst.to_string_lossy().into_owned()
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

fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("runs");
    let said = String::from_utf8_lossy(&out.stdout).to_string()
        + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

const LIMITS: &str = "agents/refund-desk/limits.yaml";
const APPROVALS: &str = "policies/approvals.yaml";

#[test]
fn the_worked_example_is_written_in_the_currency_its_price_list_charges_in() {
    // The half that matters most, and the one a check like this most easily
    // gets wrong: a correct tree must still load. A false positive on the
    // shipped shape costs an author their trust in every other line the tool
    // prints, and there is no way to earn that back.
    let (ok, said) = check(&example());
    assert!(ok, "the shipped example must still load cleanly:\n{said}");
}

#[test]
fn a_ceiling_in_a_currency_nothing_can_price_is_refused_where_the_author_wrote_it() {
    let root = edited("cap", &[(LIMITS, "cost-per-request-under: 0.05 USD", "cost-per-request-under: 500 JPY")]);
    let (ok, said) = check(&root);

    assert!(!ok, "a cap in money nothing here counts must be refused:\n{said}");
    // File and line, so the reader can open the thing they are being told about.
    assert!(said.contains("limits.yaml:11"), "name the file and the line:\n{said}");
    // The currency they wrote, quoted back on the setting they wrote it on.
    assert!(
        said.contains("`cost-per-request-under: 500 JPY`"),
        "quote the whole setting as typed:\n{said}"
    );
    assert!(said.contains("JPY"), "name the currency written:\n{said}");
    // And the currency that IS priced, because a refusal that does not say what
    // would work leaves the reader with nowhere to go (D13).
    assert!(said.contains("USD"), "name the currency that is priced:\n{said}");

    let fix = said.lines().find(|l| l.trim_start().starts_with("fix:")).expect("a fix");
    assert!(fix.contains("<amount> USD"), "the fix must be a line to type: {fix}");
    assert!(
        fix.contains("models/catalog.yaml"),
        "and must name the door out for a workspace that really does deal in JPY: {fix}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_threshold_a_person_is_asked_above_is_held_to_the_same_rule() {
    // The same blindness on the surface where it costs money. `questions._amount`
    // strips `JPY` off the rule's side and `USD` off the call's and compares the
    // bare numbers, so a `200 JPY` line gates at 200 of whatever the model wrote
    // — about 1.30 USD, on a desk whose refunds run to hundreds.
    let root = edited("threshold", &[(APPROVALS, "more-than: 200 USD", "more-than: 200 JPY")]);
    let (ok, said) = check(&root);

    assert!(!ok, "an approval threshold in unpriceable money must be refused:\n{said}");
    assert!(said.contains("approvals.yaml:"), "name the file and the line:\n{said}");
    assert!(said.contains("`more-than: 200 JPY`"), "quote the setting as typed:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_workspace_that_prices_a_model_in_its_own_currency_may_write_that_currency() {
    // The door out, and the reason this is a rule about the PRICE LIST rather
    // than a hardcoded USD. A site that genuinely deals in JPY says so the same
    // way an air-gapped site names a model this distribution has never heard of
    // — a row in its own `models/catalog.yaml`, which is data an author edits
    // and not code (D14). Without this the refusal above would be a rule that
    // only one currency in the world can satisfy.
    let root = edited(
        "own-catalogue",
        &[(LIMITS, "cost-per-request-under: 0.05 USD", "cost-per-request-under: 500 JPY")],
    );
    std::fs::create_dir_all(format!("{root}/models")).unwrap();
    std::fs::write(
        format!("{root}/models/catalog.yaml"),
        "models:\n  \
         local-jp:\n    \
         family: local-jp\n    \
         served-by:\n      \
         - { runtime: ollama, endpoint: local }\n    \
         cost: { input-per-mtok: 12 JPY, output-per-mtok: 40 JPY }\n",
    )
    .unwrap();

    let (ok, said) = check(&root);
    assert!(ok, "a workspace that prices a model in JPY may write JPY:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn every_money_field_the_specification_declares_is_one_this_check_can_see() {
    // `currency::money_fields` reads the schema for fields typed `money` and
    // holds their VALUE against the price list, so a new money field is covered
    // by a line of YAML and no Rust change — which is the whole point (F-1).
    //
    // What it cannot see is a money value nested inside a collection: the walk
    // matches on the KEY, and the items of a `list of money` have no key of
    // their own. The specification has no such field today, and the day it grows
    // one this fails HERE — where somebody is adding it — rather than as a
    // ceiling in the wrong money loading cleanly a year later.
    const SPEC: &str = include_str!("../../../spec/schema.yaml");
    for shape in ["list of money", "map of money"] {
        assert!(
            !SPEC.contains(&format!("type: {shape}")),
            "`type: {shape}` is now in spec/schema.yaml, and \
             crates/pact-loader/src/currency.rs only reaches a money value written \
             directly under its own key. Teach `walk` to look inside a {shape} \
             before shipping the field."
        );
    }
}

#[test]
fn a_ceiling_with_no_currency_on_it_is_still_one_message_and_not_two() {
    // `schema/wrong-type` already fires at that line with *"Write it like
    // `0.05 USD`"*. A second sentence about a currency nothing can price would
    // send the reader looking for a currency they did not write — two things to
    // fix for one edit, and the second one imaginary.
    let root = edited("no-currency", &[(LIMITS, "cost-per-request-under: 0.05 USD", "cost-per-request-under: 0.05")]);
    let (ok, said) = check(&root);

    assert!(!ok, "a bare number is still refused:\n{said}");
    assert!(
        !said.contains("loader/currency-nothing-can-price"),
        "one mistake gets one message:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}
