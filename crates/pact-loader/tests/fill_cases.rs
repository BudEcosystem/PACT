//! An agent's words, filled for one run, held to the shared cases
//! (`tests/conformance/fill.json`) that `pact_adapters.holes.fill` blesses and
//! the WebAssembly build replays: a template reads the same to a model whichever
//! runtime fills it.

use pact_loader::fill::{FillError, Language, fill};
use serde_json::{Map, Value, json};

fn cases() -> Vec<Value> {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/conformance/fill.json"
    );
    let held: Value = serde_json::from_str(&std::fs::read_to_string(path).expect("fill.json"))
        .expect("fill.json is JSON");
    held["cases"].as_array().expect("cases").clone()
}

fn values(case: &Value, key: &str) -> Map<String, Value> {
    case[key].as_object().cloned().unwrap_or_default()
}

#[test]
fn every_shared_case_is_what_this_port_fills() {
    let mut wrong = Vec::new();
    for case in cases() {
        let language = Language::written(case["language"].as_str());
        let got = match fill(
            case["text"].as_str().expect("text"),
            language,
            &values(&case, "run-inputs"),
            &values(&case, "remembers"),
        ) {
            Ok(said) => json!({ "said": said }),
            Err(FillError::Unfilled { .. }) => json!({ "refused": "unfilled" }),
            Err(FillError::NotRendered(_)) => json!({ "refused": "not-rendered" }),
        };
        if got != case["expect"] {
            wrong.push(format!(
                "{}: expected {}, filled {}",
                case["name"], case["expect"], got
            ));
        }
    }
    assert!(wrong.is_empty(), "{}", wrong.join("\n"));
}
