//! The detector dialect held to the shared cases
//! (`tests/conformance/detectors.json`): `pact check` refuses exactly the
//! patterns every other port refuses, with the same reason, so a tree that
//! passes the checker detects the same values on every runtime.

use pact_loader::dialect::outside;
use serde_json::Value;

fn cases() -> Vec<Value> {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/conformance/detectors.json"
    );
    let held: Value =
        serde_json::from_str(&std::fs::read_to_string(path).expect("detectors.json"))
            .expect("detectors.json is JSON");
    held["cases"].as_array().expect("cases").clone()
}

#[test]
fn every_shared_case_is_in_or_outside_the_dialect_for_the_same_reason() {
    let mut wrong = Vec::new();
    let all = cases();
    for case in &all {
        let pattern = case["looks-like"].as_str().expect("looks-like");
        let expected = case["outside"]
            .as_bool()
            .expect("outside")
            .then(|| case["reason"].as_str().expect("reason").to_string());
        let got = outside(pattern).map(|refused| refused.reason);
        if got != expected {
            wrong.push(format!("`{pattern}`: expected {expected:?}, read {got:?}"));
        }
    }
    assert!(all.len() > 80, "the shared cases are missing");
    assert!(wrong.is_empty(), "{}", wrong.join("\n"));
}
