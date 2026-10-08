# a-bundle-that-brings-a-pattern

A workspace that mounts a bundle whose approval rule is a **pattern**: the
rule's figure is a hole (`more-than: <limit>`) that each workspace fills with
`based-on: approval-limit` and `with: {limit: 500 USD}`.

```
bundles/approvals-kit/approvals-kit.yaml
bundles/approvals-kit/contributes/policies/approval-limit.yaml     <- the pattern
bundles/approvals-kit/contributes/questions/approve-this-request.yaml
```

A pattern in a workspace is held to its own declarations and then removed, so
the rule checked is the one made from it, with the figure filled in. A pattern
a bundle contributes stays where it was written, and the loader used to check
it as a finished rule: `<limit>` is not a figure, so the bundle was refused
(`loader/threshold-is-not-a-figure`). It is now checked as a pattern, the same
way: a hole it declares is right, and a hole it does not declare is refused
(`loader/a-hole-nothing-fills`).

```bash
cargo run -p pact-cli -- check --deny-warnings tests/trees/a-bundle-that-brings-a-pattern
```

Held by `crates/pact-cli/tests/a_pattern_a_bundle_brings_is_checked_as_a_pattern.rs`.
