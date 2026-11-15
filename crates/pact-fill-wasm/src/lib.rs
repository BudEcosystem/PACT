//! **`pact_loader::fill` as a WebAssembly module**: an agent's words, filled for
//! one run, in the process of a runtime that is not Rust (`adapters/typescript/
//! src/fill.ts`, a browser), with the same engine `pact check` reads templates
//! with and `pact fill` prints.
//!
//! Built with `cargo build -p pact-fill-wasm --target wasm32-unknown-unknown
//! --release`; the module imports nothing. A host:
//!
//! 1. asks for `len` bytes with `pact_alloc(len)`, which returns their address;
//! 2. writes the request there as UTF-8 JSON —
//!    `{"text", "language", "run-inputs", "remembers"}`, the fields of a case in
//!    `tests/conformance/fill.json`;
//! 3. calls `pact_fill(address, len)`, which takes the request's bytes back and
//!    returns the answer as `address << 32 | len`: UTF-8 JSON, `{"said": …}` or
//!    `{"refused": "unfilled" | "not-rendered", "message": …}`;
//! 4. reads the answer and gives its bytes back with `pact_free(address, len)`.

use pact_loader::fill::{FillError, Language, fill};
use serde_json::{Map, Value, json};

/// The answer to one request, as JSON text.
pub fn answer(request: &str) -> String {
    let request: Value = match serde_json::from_str(request) {
        Ok(value) => value,
        Err(e) => {
            return json!({ "refused": "not-rendered", "message": format!("the request is not JSON: {e}") })
                .to_string();
        }
    };
    let values = |key: &str| -> Map<String, Value> {
        request
            .get(key)
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default()
    };
    let text = request.get("text").and_then(Value::as_str).unwrap_or("");
    let language = Language::written(request.get("language").and_then(Value::as_str));
    match fill(text, language, &values("run-inputs"), &values("remembers")) {
        Ok(said) => json!({ "said": said }),
        Err(why @ FillError::Unfilled { .. }) => {
            json!({ "refused": "unfilled", "message": why.to_string() })
        }
        Err(why @ FillError::NotRendered(_)) => {
            json!({ "refused": "not-rendered", "message": why.to_string() })
        }
    }
    .to_string()
}

/// `len` bytes the host may write a request into; the address of the first.
#[unsafe(no_mangle)]
pub extern "C" fn pact_alloc(len: usize) -> *mut u8 {
    let mut bytes = Vec::<u8>::with_capacity(len);
    let at = bytes.as_mut_ptr();
    std::mem::forget(bytes);
    at
}

/// Give back `len` bytes at `at` that `pact_alloc` or `pact_fill` handed out.
///
/// # Safety
///
/// `at` and `len` are exactly an allocation this module handed out and has not been given back.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn pact_free(at: *mut u8, len: usize) {
    // SAFETY: the caller hands back an allocation of `len` bytes from `pact_alloc`, or the answer
    // of `pact_fill`, whose capacity is its length (`into_boxed_slice`).
    drop(unsafe { Vec::from_raw_parts(at, 0, len) });
}

/// Fill the request of `len` bytes at `at` and free it; the answer as `address << 32 | len`.
///
/// # Safety
///
/// `at` and `len` are an allocation from `pact_alloc` holding the request, which this call gives
/// back; the host must not use it again.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn pact_fill(at: *mut u8, len: usize) -> u64 {
    // SAFETY: the caller wrote `len` bytes into an allocation of `len` bytes from `pact_alloc`.
    let request = unsafe { Vec::from_raw_parts(at, len, len) };
    let said = answer(&String::from_utf8_lossy(&request))
        .into_bytes()
        .into_boxed_slice();
    let (len, at) = (said.len(), Box::into_raw(said).cast::<u8>());
    // Addresses and lengths fit in 32 bits on wasm32, the only target this is built for.
    ((at as usize as u64) << 32) | len as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_request_is_answered_as_the_shared_cases_say() {
        let request = r#"{"text": "Hi {{run-inputs.name}}", "language": "holes", "run-inputs": {"name": "Ada"}}"#;
        assert_eq!(answer(request), r#"{"said":"Hi Ada"}"#);
        let refused: Value = serde_json::from_str(&answer(
            r#"{"text": "{{ run_inputs.x }}", "language": "jinja"}"#,
        ))
        .unwrap();
        assert_eq!(refused["refused"], "unfilled");
        let broken: Value = serde_json::from_str(&answer("not json")).unwrap();
        assert_eq!(broken["refused"], "not-rendered");
    }
}
