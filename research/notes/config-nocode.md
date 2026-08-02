# Research stream: `config-nocode`

**Question owned:** what makes declarative configuration usable — or unusable — by a
non-technical domain expert (D13) who must nonetheless build a *complete* multi-agent
system with custom tools, evals, SLOs and learning **in YAML/Markdown alone** (D14),
**fully offline** (D17), across **four author surfaces** (D18), where the **file tree is
the native form** (D2).

**Corpus read (source, not READMEs):**
`research/repos/config/{cel-spec,cue,kcl,pkl,jsonnet,dhall-lang,opa,kubevela,crossplane}`,
`research/repos/protocols/{json-schema-spec,serverless-workflow,oam-spec}`.

**Evidence discipline.** Every claim below carries `path:line`. Paths are relative to
`/home/bud/ditto/agent-inter-op/research/repos/` unless absolute. Claims I did not
execute are marked **[inferred]** with the reasoning shown.

**Repo freshness** (`git log -1`, checked 2026-07-26): cue 2026-07-23, kcl 2026-07-24,
pkl 2026-07-24, opa 2026-07-23, kubevela 2026-07-23, crossplane 2026-07-24, cel-spec
2026-07-20, dhall-lang 2026-07-19, jsonnet 2026-03-27, serverless-workflow 2026-07-23,
json-schema-spec 2026-07-14, **oam-spec 2024-12-24 (dormant ~19 months)**.

---

## 0. Executive verdict (the five answers)

| # | Question | Verdict |
|---|---|---|
| 1 | Does PACT need an expression language? | **No, not on the no-code path.** Ship **structured predicates** (typed atoms, implicit AND) as the *only* form a non-coder ever writes. Add a **restricted CEL profile** (no macros, no arithmetic, no string builders) as an *expert-tier, optional* escape that desugars *from* structured predicates and is always displayed back as structured predicates. CEL is chosen over jq/CUE/Rego on evidence, but is **not the authoring surface**. |
| 2 | Validation strategy for actionable errors | JSON Schema for **shape**, PACT-owned **rule catalogue** for **messages**. JSON Schema deliberately refuses to specify messages. Copy KCL/Pkl: stable error code + primary span + **secondary span at the rule's own declaration** + did-you-mean from the closed key set + one-line "how to fix". Report **all** errors by default (CUE's `-E` default is a documented usability bug). |
| 3 | Defaulting / inheritance / overlay | **One linear amend chain, replace-by-default, explicit `merge:` opt-in, key-based (never index-based) list identity, at most one instance of a kind per parent.** Reject unification-style defaults (CUE proves two defaults for one field = hard error). Ship `pact explain <path>` (Dhall normal-form idea) as the antidote to non-locality. |
| 4 | Control flow without becoming a bad language | A **closed 8-verb task vocabulary**, sequence-by-declaration-order, **structured-only jumps (no cross-scope goto)**, and a **single data plane**. Crossplane's own post-mortem is the load-bearing evidence: refusing an escape hatch does not prevent a DSL, it just produces a *bad accreted* one. |
| 5 | YAML vs alternatives | **YAML 1.2 core schema, restricted profile, as the only author-facing syntax.** No embedded second language in string literals (KubeVela's `template: \|` CUE-in-YAML is the anti-pattern). Ordered things are arrays with a `name:` key; unordered things are maps. PACT's Rust core needs a **comment/format-preserving CST YAML editor**, because the dominant Rust crate is unmaintained and comment-lossy. |

---

## 1. Expression languages

### 1.1 What the corpus actually uses

| System | Expression language | Where it appears | Read from |
|---|---|---|---|
| Crossplane | **CEL** (`XValidation`) | 49 rules across the API | `config/crossplane/apis/**/*_types.go` |
| Kubernetes/KubeVela | **CEL** (CRD validation) + **CUE** (templates) + **CUE-as-`if`-string** (workflow steps) | 3 different languages in one product | `config/kubevela/design/vela-core/appfile-design.md:74`, `config/kubevela/docs/examples/workflow/app-with-if/README.md:38` |
| Serverless Workflow | **jq**, mandatory; others optional via `evaluate.language` | every task | `protocols/serverless-workflow/dsl.md:377-379` |
| OPA | **Rego** | whole product | `config/opa/v1/ast/` |
| CUE | **CUE itself** (unification, disjunction, comprehension) | whole product | `config/cue/doc/ref/spec.md` |
| Pkl | **Pkl itself** (typed constraints `Int(this >= min)`) | whole product | `config/pkl/pkl-core/src/test/files/LanguageSnippetTests/output/classes/constraints5.err` |
| KubeVela UI layer | **3 operators only** (`==`, `!=`, `in`) | form field enable/disable | `config/kubevela/pkg/utils/schema/ui_schema.go:71,89` |
| Kubernetes label selectors | **no language** — `{key, operator, values}` atoms, "requirements are ANDed" | selectors everywhere | CRD text at `config/kubevela/pkg/workflow/providers/legacy/query/testdata/gateway/crds/gateway.networking.k8s.io_gateways.yaml:222-247` |

### 1.2 The CEL evidence, in detail

**What CEL gets right (verified in spec):**
- Grammar is ~26 lines of BNF (`config/cel-spec/doc/langdef.md:26-52`).
- "memory-safe … side-effect-free … **terminating** … strongly-typed … gradually-typed"
  (`langdef.md:8-19`). "evaluates in linear time, is mutation free, and **not
  Turing-complete**" (`config/cel-spec/README.md:16-20`).
- Per-AST-node source positions exist (`proto/cel/expr/syntax.proto:354-356`) and
  macro expansions are back-mapped to their original call
  (`syntax.proto:358-365`) — so *building* a good error renderer on top of CEL is
  possible.
- Implementations may cap or **disable macros entirely** (`langdef.md:899-902`), which
  is the sanctioned way to get a CEL-minus profile.
- **CEL has a policy format with `explanation` per match arm**
  (`proto/cel/policy/policy.proto:47-58`: `Match{condition, output|rule, explanation}`).
  This is the single most directly copyable artifact in the whole corpus for PACT.

**What CEL gets wrong for a non-coder (verified):**

1. **Only two runtime errors exist, and neither is explanatory.**
   `no_matching_overload` and `no_such_field` are the entire built-in error vocabulary;
   "There is no in-language representation of errors, no generic way to raise them, and
   no way to catch or bypass errors" (`langdef.md:646-654`). A failing predicate returns
   **`false`**, with no account of *which conjunct* failed or *what the actual value was*.

2. **The "explain" mechanism is deprecated upstream.**
   `proto/cel/expr/explain.proto:29` — `option deprecated = true;` on the entire
   `Explain` message, which was the only standard way to surface intermediate values.
   ⇒ **If PACT uses CEL it must build its own sub-expression value tracer.** Nobody
   upstream will provide it.

3. **`MMLU > 80` — the exact PACT example — is a type error in strict CEL.**
   "Comparisons require strict type equality at type-check time … The one exception to
   this rule is numeric comparisons **at runtime**" (`langdef.md:1532-1541`). The
   conformance suite confirms: `'foo' < 1024` needs `disable_check: true` and yields
   `no such overload` (`tests/simple/testdata/comparisons.textproto:1227-1234`), and
   **every** cross-type comparison test is written as `dyn(1) < 2.0`,
   `dyn(2) > 1.0`, … (`comparisons.textproto:1241-1243, 1483-1490`). If the model
   catalogue declares `MMLU: double` and the author types `> 80` (an int literal), a
   type-checked CEL environment rejects it with **`no such overload`** — the worst
   possible message for a support lead. *Mitigation exists* (declare catalogue
   variables as `dyn`, or normalise all benchmark figures to `double` and coerce integer
   literals), but it is a mitigation PACT must consciously implement, not a default.

4. **`&&` / `||` are commutative, not short-circuiting.**
   "if any of their operands uniquely determines the result … the other operand may or
   may not be evaluated, and if that evaluation produces a runtime error, **it will be
   ignored**" (`langdef.md:661-668`). The guard idiom `has(x) && x > 5` that every
   programmer reaches for is *not* what CEL does; to get McCarthy evaluation you must
   write `e1 ? e2 : false` (`langdef.md:670-673`). A non-coder cannot be expected to
   know this, and worse, the forgiving behaviour **silently swallows errors** — directly
   hostile to T7 (structural honesty) and D11 (fail, then recommend).

5. **Order of error propagation is unspecified.** "it will propagate one or more of the
   sub-expression errors, but **it is not specified which ones**" (`langdef.md:604-608`).
   Two conformant CEL implementations may report different errors for the same bad
   predicate. For a spec whose adapters live out-of-tree in Python/TS/Rust (D4), that is
   a conformance hazard.

6. **17 reserved words that look like ordinary field names**: `as break const continue
   else for function if import let loop package namespace return var void while`
   (`langdef.md:145-146`). A PACT capability named `import` or `function` would be
   unusable inside an expression.

7. **CEL's own stated audience is developers**: "The language is approachable **to
   developers**. The initial spec was based on the experience of developing Firebase
   Rules" (`config/cel-spec/README.md:25-27`).

### 1.3 The empirical minimum: what real config APIs actually use

Crossplane has 49 `XValidation` CEL rules. The *entire* construct set they use:

```
has(x)                  self == oldSelf         !(a && b)
a && b   a || b   !a    a == b   a != b
size(self) > 0          self.plural == self.plural.lowerAscii()
```
Sources: `config/crossplane/apis/apiextensions/v1/xrd_types.go:39-52`,
`apis/apiextensions/v1/composition_types.go:25,29`,
`apis/protection/v1beta1/usage_types.go:121-130`,
`apis/pkg/v1beta1/image_config_types.go:76`,
`apis/apiextensions/v1alpha1/mrd_types.go:36`.

**Every single one carries an author-written `message=` in plain English.** Examples,
verbatim:
- `"an array of pipeline steps is required in Pipeline mode"`
- `"name and matchLabels are mutually exclusive"`
- `"either a resource reference or a resource selector should be set."`
- `"Only LegacyCluster composite resources can offer claims"`
- `"state cannot be changed once it becomes Active"`
- `"Plural name must be lowercase"`

**Finding:** a mature, heavily-used declarative API needs **~8 boolean/relational
constructs, `has()`, `size()`, one string function, and `oldSelf`** — plus a mandatory
human message per rule. Zero arithmetic, zero comprehensions, zero macros, zero string
interpolation. This is the size of the expression language PACT actually needs, and it
is small enough to be a *data structure* rather than a *grammar*.

Corroboration from the UI tier: KubeVela's shipped form-conditional language is exactly
**three operators** — `==`, `!=`, `in` — validated by an explicit allowlist
(`config/kubevela/pkg/utils/schema/ui_schema.go:71`, enforced at `:89`), with
`action: enable|disable` and documented precedence rules at `:53-58`.

Corroboration from Kubernetes: `matchExpressions` is `{key, operator ∈ {In, NotIn,
Exists, DoesNotExist}, values[]}` with "**The requirements are ANDed**" — a
zero-parser predicate language that has survived a decade at planetary scale
(CRD text: `config/kubevela/pkg/workflow/providers/legacy/query/testdata/gateway/crds/gateway.networking.k8s.io_gateways.yaml:222-247`).

### 1.4 jq (Serverless Workflow) is disqualified

- Mandated as the default and only guaranteed language (`protocols/serverless-workflow/dsl.md:377`).
- **The spec's own normative examples are inconsistent about `${}` delimiters.**
  Strict mode "all expressions must be properly identified with `${}` syntax"
  (`dsl.md:375`), yet `dsl-reference.md:710` writes `while: .vet != null` and
  `dsl-reference.md:1140` writes `when: .orderType == "electronic"` — both bare — while
  `dsl-reference.md:752` writes `patientId: ${ .patient.fullName }`. Same document.
  A non-coder cannot infer the rule.
- Expression-argument availability is a **7×8 matrix** the author must memorise
  (`dsl.md:451-459`): `$output` is available in `export.as` but not in `output.as`;
  `$secrets` is available only in workflow `input.from`; `$authorization` only after the
  task definition stage.
- jq's `.` context re-binds at every one of the 11 data-flow stages
  (`dsl.md:239-283`), so the *same* expression text means different things in different
  fields.

### 1.5 CUE / Pkl / Rego as the predicate language — rejected

- **CUE**: the semantics you need to reason about a default are 10 rewrite rules
  (`config/cue/doc/ref/spec.md:783-804`) plus a subsumption lattice (`:825-832`), and
  the canonical failure `(*1|2) & (1|*2) ⇒ ⟨1|2, _|_⟩` (`spec.md:820`) means **two
  layers each declaring a different default for one field is a hard error, not a
  resolution.** Also: writing a constraint with a message requires the disjunction idiom
  `x: int | error("I wanted an integer")` (`config/cue/cue/testdata/builtins/error.txtar:81`),
  which no non-coder will produce.
- **Pkl**: constraint syntax is `Int(this >= min)`
  (`config/pkl/pkl-core/src/test/files/LanguageSnippetTests/output/classes/constraints5.err`)
  — a type-with-embedded-predicate. Excellent error rendering (see §2), but the language
  is a full functional language with classes, `amends`, late binding, `local`, `fixed`,
  `const`, `hidden`, and JVM/GraalVM runtime weight.
- **Rego**: canonical error is `var x is unsafe` (`config/opa/v1/ast/compile.go:1619,7343`).
  OPA itself acknowledges opacity by bolting a case-specific hint onto one instance:
  `"var %[1]v is unsafe (hint: \`import future.keywords.%[1]v\` to import a future
  keyword)"` (`compile.go:7339-7340`). Datalog semantics (unification, negation-as-failure,
  rule ordering irrelevance) are further from a support lead's mental model than any
  other candidate.

### 1.6 Recommendation — the two-tier predicate model

**Tier 0 (the only no-code surface): structured predicates.** A predicate is a *list of
typed atoms*, implicitly AND-ed, each of which is a small closed record. `MMLU > 80 &&
SWE-Verified > 40 && context >= 128k` becomes:

```yaml
requires:
  - benchmark: MMLU            # atom kind: benchmark
    at_least: 80
  - benchmark: SWE-Verified
    at_least: 40
  - context_window:
      at_least: 128k
  - capability: tool_calling
    mode: parallel
```

Properties this buys, each traceable to evidence:
- **No parser, no injection surface.** Satisfies the Serverless Workflow security
  requirement verbatim: "Runtimes **must not** parse or evaluate expression syntax
  embedded in workflow input or task input data … exposes the system to injection
  attacks" (`protocols/serverless-workflow/dsl.md:385-386`).
- **Per-atom failure messages are mechanical**, so PACT can emit
  `MMLU is 74.1 for qwen3-4b; you require at least 80` without any tracing machinery —
  which matters because CEL's tracing machinery is deprecated (`explain.proto:29`).
- **Forms render for free**: each atom is one row; the operator is a `Select` from a
  closed enum, exactly KubeVela's `GetDefaultUIType` mapping
  (`config/kubevela/pkg/utils/schema/ui_schema.go:128-155`).
- **Diffs are line-oriented** (D18): changing a threshold changes one line.
- **Builder agents emit it reliably** — it is JSON-shaped data, not a string to be
  lexed.
- **No cross-type comparison trap**: `at_least: 80` is compared by PACT's own
  typed comparator against a `double`, so the CEL `dyn()` problem
  (`comparisons.textproto:1241`) cannot arise.

**Composition beyond AND.** Keep it structural, not textual:
```yaml
requires:
  all_of: [ … ]        # default when `requires:` is a bare list
  any_of: [ … ]
  none_of: [ … ]
```
Three combinators, nestable, mirroring JSON Schema's `allOf`/`anyOf`/`not` so the schema
and the predicate language share one mental model.

**Tier 1 (expert escape, never required — D14 compliant because Tier 0 is complete):**
a `cel:` field accepting a **restricted CEL profile**:
- Macros **disabled** (sanctioned at `langdef.md:899-902`) ⇒ no exponential blowup, no
  comprehension scoping rules to learn.
- Arithmetic, string concatenation, and list/map construction **disabled** ⇒ removes the
  only operator that blows up space (`langdef.md:903-905`).
- Allowed: `== != < <= > >= in`, `&& || !`, `?:`, `has()`, `size()`, field selection,
  literals. This is a superset of the 8 constructs Crossplane actually needs.
- All catalogue numerics declared `double`; all integer literals promoted at compile
  time. Verified necessary by `comparisons.textproto:1227-1243`.
- **`&&`/`||` must be lowered to `?:` before evaluation** so PACT gets left-to-right
  short-circuit and does *not* inherit CEL's error-swallowing commutativity
  (`langdef.md:661-673`). The spec text gives the exact rewrite.
- **Every Tier-1 expression must round-trip to Tier 0 when it is expressible there**, and
  the UI must render it as structured atoms. Otherwise Tier 1 becomes the de-facto
  surface and D14 is lost.

**Every predicate — Tier 0 or Tier 1 — carries a mandatory `because:` string**, exactly
Crossplane's `message=` (49/49 rules) and CEL-policy's `explanation`
(`proto/cel/policy/policy.proto:57`).

**Air-gap note (D17).** CEL's canonical AST serialization is protobuf
(`config/cel-spec/README.md:44-50`) and the reference implementations are Go/Java/C++.
A Rust core (D4) evaluating Tier-1 CEL needs either a vendored Rust CEL or an
out-of-process evaluator. Tier 0 needs neither — it is a Rust `match`. **This is a
further reason to make Tier 0 total and Tier 1 optional.** *(I found no Rust CEL
implementation in the local corpus; the conformance suite exists as textproto at
`config/cel-spec/tests/simple/testdata/` and can gate any Rust implementation offline.)*

---

## 2. Schema and validation: error messages a non-coder can act on

### 2.1 JSON Schema deliberately does not solve this

The output specification defines **structure only** — `evaluationPath`,
`schemaLocation`, `instanceLocation`, `valid`, `errors`, `details`
(`protocols/json-schema-spec/specs/output/jsonschema-validation-output-machines.md:37-53,
84-96`) — and then explicitly disclaims wording:

> "the error message wording as depicted in the examples below is **not a requirement of
> this specification**. Implementations SHOULD craft error messages tailored for their
> audience **or provide a templating mechanism that allows their users to craft their
> own messages**."
> — `jsonschema-validation-output-machines.md:180-185`

The core spec repeats the deferral: "this specification defers the details of any output
formats to other documents" (`specs/jsonschema-core.md:1955-1958`).

**⇒ PACT must own the message layer.** JSON Schema is a good *shape* checker and a good
*location* reporter; it is not, and does not claim to be, a UX.

Three further JSON Schema traps that hit PACT specifically:

1. **`additionalProperties` does not see through composition.** "The behavior of this
   keyword depends on the presence of `properties` and `patternProperties` **within the
   same schema object**" (`jsonschema-core.md:1780-1783`). So the natural PACT idiom
   `allOf: [{$ref: '#/agentBase'}, {additionalProperties: false}]` rejects *every*
   inherited field. The fix, `unevaluatedProperties`, "depends on **all adjacent
   keywords as well as keywords in successfully validated subschemas**"
   (`jsonschema-core.md:1931-1935`) — i.e. it is annotation-dependent, which is why
   implementations diverge on it.
2. **`anyOf`/`oneOf` error explosion.** The "list" and "hierarchical" formats emit an
   output unit per failing branch (`…output-machines.md:62-83`). A closed union of 8
   task kinds produces 8 failure reports for one typo. PACT must **discriminate before
   validating** (see §2.4).
3. **Flag format short-circuits.** "it is RECOMMENDED that implementations use
   short-circuiting logic to return failure … as soon as the outcome can be determined"
   (`…output-machines.md:238-242`). Fine for machines, fatal for authors.

### 2.2 The best error messages in the corpus: KCL

Real golden output, not documentation
(`config/kcl/tests/grammar/schema/type/type_fail_0/stderr.golden`):

```
error[E2G22]: TypeError
 --> ${CWD}/main.k:7:5
  |
7 |     "lastName": "Doe"
  |     ^ expected int, got str(Doe)
  |
 --> ${CWD}/main.k:3:5
  |
3 |     lastName: int
  |     ^ variable is defined here, its type is int, but got str(Doe)
  |
```

Six things this does right, all of which PACT should copy:
1. **Stable machine code** `E2G22` — resolvable to a documentation page. KCL ships those
   pages in-repo as Markdown: `config/kcl/crates/error/src/error_codes/E2G22.md` (12 error
   codes + 1 warning code as of this checkout).
2. Primary span with a caret at the *offending value*.
3. **Expected vs got, with the actual value inlined** (`got str(Doe)`, not `got str`).
4. **A second span pointing at the declaration that was violated** — "variable is defined
   here". This is the single most under-used technique in the corpus and is *exactly*
   what a non-coder needs: it answers "says who?".
5. The docs pages carry a **"Possible resolution:"** section
   (`config/kcl/crates/error/src/error_codes/E2D34.md`, `E1001.md`).
6. **Did-you-mean, computed from the closed key set**:
   `Cannot add member 'frist' to schema 'Person', did you mean '["first"]'?`
   (`config/kcl/tests/grammar/schema/mixin/add_member_fail/stderr.golden`). Implementation:
   `config/kcl/crates/sema/src/resolver/attr.rs:128-160` collects `schema_ty.attrs.keys()`
   then calls `suggestions::provide_suggestions` (crate `suggestions = "0.1.1"`,
   `config/kcl/crates/sema/Cargo.toml:34`). Same technique at
   `crates/sema/src/resolver/scope.rs:430-446`, `resolver/config.rs:460,488`,
   `resolver/arg.rs:171`.

**And two things it gets wrong**, which are the cautionary half:
- `can't change schema field type of 'firstName' from int to int`
  (`config/kcl/tests/grammar/schema/inherit/inherit_change_field_type_0/stderr.golden:6`) —
  a nonsense message shipped in a golden file. **Format is not content**; every message
  string needs its own review.
- The suggestion is Rust-`Debug`-formatted: `'["first"]'` rather than `'first'`.
  Message *rendering* needs the same care as message *authoring*.

### 2.3 The best failure *explanation* in the corpus: Pkl

`config/pkl/pkl-core/src/test/files/LanguageSnippetTests/output/classes/constraints5.err`:

```
–– Pkl Error ––
Type constraint `this >= min` violated.
Value: 3

    this >= min
    │    │  │
    3    │  4
         false

x | max: Int(this >= min)
             ^^^^^^^^^^^
at constraints5#Gauge.max (…)
```

This is a **sub-expression value trace**: every operand's runtime value is printed under
the operator that consumed it, and the operator's own result (`false`) is printed too.
For `MMLU > 80 && SWE-Verified > 40` this is precisely the output PACT needs when a
resolver refuses to bind a model — and it is precisely what CEL cannot give you
(`explain.proto:29`, deprecated).

Pkl also externalises its whole message catalogue: **1,210 lines** in
`config/pkl/pkl-core/src/main/resources/org/pkl/core/errorMessages.properties`, with a
disciplined naming convention and *graded* variants per situation, e.g.
(`errorMessages.properties:367-405`):
- `cannotFindPropertyInScope` — bare
- `cannotFindPropertyInScopeListCandidates` — + "Did you mean any of the following?"
- `cannotFindPropertyInModule` — + "Available properties in module `{1}`:"
- `cannotFindPropertyInObjectNoHint` — explicitly hint-free variant

Real rendered output with suggestions:
`config/pkl/pkl-core/src/test/files/LanguageSnippetTests/output/mappings2/stringKeyNotFound.err`
and `.../errors/functionNotFoundInModule.err`.

**The Pkl anti-pattern to avoid:** *every* error ends with two frames of implementation
internals —
```
xxx | renderer.renderDocument(value)
at pkl.base#Module.output.text (pkl:base)
xxx | if (renderer is BytesRenderer) renderer.renderDocument(value) else …
at pkl.base#Module.output.bytes (pkl:base)
```
— present in all four `.err` files I read. A support lead reading this concludes the
tool is broken. **PACT must have an explicit "user frames only" filter on stack
rendering.**

### 2.4 The failure modes to design against — CUE as the negative control

CUE is the most powerful validator in the corpus and produces the least actionable
messages:

| Real CUE output | File:line | Why a non-coder is stuck |
|---|---|---|
| `bar: 2 errors in empty disjunction:` | `config/cue/cmd/cue/cmd/testdata/script/eval_errs.txtar:7` | "disjunction" is not a word in the user's vocabulary; the count is a red herring |
| `conflicting values "str" and int (mismatched types string and int)` | `eval_errs.txtar:8` | Says *what* conflicts, never *which one you should change* |
| `translations.hello.lang: incomplete value string:` | `.../vet_file.txtar:8` | "incomplete value" = "you didn't fill this in", but does not say so |
| `field not allowed:` | `config/cue/cue/testdata/fulleval/035_optionals_with_label_filters.txtar:35` | **No did-you-mean anywhere in CUE.** Grep for `did you mean` in CUE finds hits only in cobra CLI arg handling (`cmd/cue/cmd/testdata/script/unknown_args.txtar:53`), never in the evaluator |
| `2 errors in empty disjunction::` (double colon) | `config/cue/cue/testdata/builtins/error.txtar:113` | Cosmetic, but shipped |

CUE *does* have `error("custom message")`, and it works
(`config/cue/cue/testdata/builtins/error.txtar:8,30,81`). Two problems:
1. The idiom is `x: int | error("I wanted an integer")` — a disjunction with bottom.
   Expert-only syntax.
2. **Aggregation is inconsistent, admitted by CUE's own maintainers.** With three
   constraint/message pairs on one field, the output is
   `2 errors in empty disjunction` reporting only two of the three, and the test file
   carries the maintainer note: *"we could also include the third condition, if we want
   to be consistent."* (`error.txtar:81-90`, `hint=` on the `@test` directive).
   There is also an open case where a user `error()` inside a pattern constraint is
   *lost* and the generic `field not allowed` is shown instead — filed as
   cuelang.org/issue/4208, encoded as a `@test(err:todo, …)` expectation at
   `config/cue/cue/testdata/builtins/issue4208.txtar:1-2,15`.

**And the biggest single usability defect in the corpus:**

> `AllErrors causes all errors to be reported (**not just the first 10 on different
> lines**)` — `config/cue/cue/parser/interface.go:132-133`
> `// AllErrors continues descending into a Vertex, even if errors are found.` —
> `config/cue/internal/core/adt/validate.go:31-32`, gated at `:104`
> CLI default is **off**: `f.BoolP("all-errors", "E", false, …)` —
> `config/cue/cmd/cue/cmd/flags.go:104`

A non-coder fixing a 3-agent workspace therefore gets one error, fixes it, gets another,
fixes it… **PACT must report every independent error in one pass, by default, with no
flag.**

### 2.5 Recommended validation strategy for PACT

**Pipeline (all offline, D17):**

```
tree ──► CST parse (positions kept) ──► discriminate by `kind:` ──►
   shape check (JSON Schema, per-kind, closed) ──►
   key check (closed key set + did-you-mean) ──►
   reference check (all `$ref`/name lookups resolve) ──►
   rule check (PACT rule catalogue; structured predicates + Tier-1 CEL) ──►
   report ALL findings, sorted by file/line
```

**Discriminate before validating.** Never present a bare `oneOf` to the author. Every
polymorphic node carries an explicit discriminator (`kind:`, `type:`), the loader selects
one schema, and validation errors are reported against *that* schema only. This
eliminates the `anyOf` error explosion described at
`…output-machines.md:62-83` and is why the Serverless Workflow, OAM and Crossplane
models are all discriminator-first (`type:` on traits at
`protocols/oam-spec/6.traits.md:40-42`; `call:`/`do:`/`switch:` as the task
discriminator at `protocols/serverless-workflow/dsl.md:168-181`).

**The PACT diagnostic record** (normative shape — every emitter must fill all fields):

```yaml
code: PACT-E0142                    # stable, documented, greppable  (KCL E2G22)
severity: error | warning
title: "Unknown field 'temprature' on agent"
where:                              # PRIMARY span — the thing the author typed
  file: agents/researcher/agent.yaml
  line: 12
  col: 3
  excerpt: "  temprature: 0.7"
because:                            # SECONDARY span — the rule that rejected it
  file: <builtin>/schema/agent.yaml
  line: 88
  note: "the Agent kind declares 14 fields; 'temprature' is not one of them"
actual: 0.7                         # value inlined, KCL style
expected: "one of: temperature, top_p, top_k, …"
suggestion:                         # did-you-mean, from the closed key set
  did_you_mean: temperature
  fix: "rename 'temprature' to 'temperature'"
docs: pact://errors/E0142
```

Rules, each with its evidence:
- **Stable code + in-repo docs page.** KCL ships them as Markdown under
  `crates/error/src/error_codes/`; PACT ships them under `docs/errors/` so they work
  air-gapped.
- **Two spans always.** Primary = author's text; secondary = the declaration that was
  violated. From `config/kcl/tests/grammar/schema/type/type_fail_0/stderr.golden` and
  CUE's multi-position lists (`vet_file.txtar:10-12` shows `./data.yaml:13:11` *and*
  `./vet.cue:3:31`).
- **Did-you-mean is mandatory for any closed key set**, computed from the schema, and it
  must render as a bare identifier, not a debug-formatted list
  (KCL's `'["first"]'` bug, `add_member_fail/stderr.golden`).
- **Value inlined**, KCL's `got str(Doe)` rather than `got str`.
- **Sub-expression trace on every failed predicate**, Pkl style
  (`constraints5.err`). For structured predicates this is free: report the atom, its
  observed value, and its threshold.
- **User frames only.** Never print PACT-internal evaluation frames (Pkl's `pkl:base`
  leak).
- **All errors, every run.** No `-E` (CUE's `flags.go:104`).
- **`because:` text is authorable.** Crossplane's 49/49 `message=` and CEL-policy's
  per-match `explanation` (`proto/cel/policy/policy.proto:57`) both prove the pattern.
  Any PACT policy/eval/SLO rule an *author* writes must have a `because:` field, and the
  validator must require it (an unexplained rule is an unactionable failure).

**Two-tier authorship, made explicit.** KubeVela and Crossplane both split roles and say
so: "the distinction is only important to the people *authoring* the Compositions, never
to the people *consuming* them" (`config/crossplane/design/design-doc-composition-functions.md:128-131`).
PACT's D14 forbids that split for *capability*, but not for *responsibility*: the
non-coder must be able to express everything, but the **schema and message catalogue are
PACT-authored**, not author-authored. Every message a domain expert sees comes from a
catalogue PACT wrote and tested.

---

## 3. Defaulting, inheritance and overlay semantics

### 3.1 The four models in the corpus, and how each fails

| Model | Mechanism | Default for nested maps | Default for lists | Failure mode |
|---|---|---|---|---|
| **Jsonnet** | `+` operator + 6 field separators | **replace** | replace (concat with `+:`) | `:` `::` `:::` `+:` `+::` `+:::` — merge behaviour *and* visibility encoded in punctuation |
| **CUE** | unification (`&`) + marked disjunction defaults | merge (unify) | element-wise unify | two different defaults for one field ⇒ **bottom** |
| **Pkl** | `amends` chain + late binding | merge (amend) | **index-addressed** amend | positional list overrides; non-local effects via late binding |
| **OAM/KubeVela** | typed traits, ordered, `conflictsWith` | n/a (one instance per kind) | n/a | no `requires`; trait-name/workload-param namespace collision |

**Jsonnet** — "By default nested objects are **completely replaced** when overriden"
(`config/jsonnet/doc/ref/language.html.md:479`). Opt-in deep merge with `+:`, which also
concatenates arrays (`:541`). Six separators total; "The number of colons determines the
visibility of the field" (`:541`). And `{ foo +: {…} }` with no left-hand match is
silently fine (`:543`). Desugars to `if "a" in super then super.a + b else b` (`:545`) —
i.e. the author is writing conditional inheritance in punctuation.

**CUE** — defaults are marked disjuncts (`config/cue/doc/ref/spec.md:756-762`), governed
by rewrite rules U0–U2, D0–D2, M0–M3 (`:783-804`). The killer:

```
(*1|2) & (1|*2)          ⟨1|2, _|_⟩          — spec.md:820
```

Two layers, each asserting a *different* default for the same field, unify to **bottom**.
In a PACT workspace that is: workspace profile says `temperature` defaults to 0.2, the
`small` variant says it defaults to 0.7 ⇒ hard error with the message
`2 errors in empty disjunction`. **Unification-based defaulting is disqualified for a
no-code system.**

**Pkl** — `amends` is clean for maps: "When a **dynamic** object is amended, not only can
existing properties be overridden or amended, but new properties can also be added. When
a **typed** object is amended, its properties can be overridden or amended, **but new
properties cannot be added**" (`config/pkl/docs/modules/language-reference/pages/index.adoc:832-835`).
That typed/dynamic split is exactly the closed/open-schema distinction PACT needs.

But two hazards:

1. **Lists are amended by index.**
   ```
   birds2 = (birds) {
     new { name = "Barn owl" }   // appends
     [0] { diet = "Worms" }      // amends element 0
     [1] = new { … }             // replaces element 1
   }
   ```
   (`index.adoc:1390-1412`). Insert one element at the top of the base and every override
   silently retargets. Compare Kubernetes strategic merge patch, which uses a
   `patchMergeKey` — and note the CRD text that documents per-field list behaviour
   inline: "This array is **replaced** during a strategic merge patch"
   (`…gateway.networking.k8s.io_gateways.yaml:245`). The fact that merge semantics must
   be documented *per field* is itself the smell.

2. **Late binding makes overrides non-local.** Pkl's own framing: "object properties
   behave like **spreadsheet cells**. When they are linked, changes to 'downstream'
   properties automatically propagate" (`index.adoc:770-776`). Worked example: overriding
   `eggIncubation` from `40.d` to `11.d` silently changes `adultWeightInGrams` from 4000
   to 1100 (`index.adoc:741-767`). For listings the same: overriding element 0's `diet`
   changes element 1's `diet` because element 1 was defined as `(this[0]) { … }`
   (`index.adoc:1436-1449`). **What you read in the file is not what runs.** For a
   non-coder reviewing a git diff (D18, surface 4) this is fatal: the diff shows one
   changed line and the behaviour change is elsewhere.

**OAM traits** — the most predictable model in the corpus, and the one to copy:
- "**A component instance may only have one configuration of any given trait type.**"
  (`protocols/oam-spec/6.traits.md:67`) ⇒ no ambiguity about which `autoscaler` wins.
- "Apply the traits in the **defined order**" and "Determine compatibility, and **fail**
  if the combination of traits cannot be satisfied" (`6.traits.md:60-65`).
- `conflictsWith: []string` declared **on the trait definition**, not discovered at merge
  time (`6.traits.md:31`).
- Ordering is preserved by representation choice, stated in the Go type:
  `// Traits define the trait of one component, **the type must be array to keep the
  order**` (`config/kubevela/apis/core.oam.dev/common/types.go:363`).
- **Negative:** "There is **no mechanism for explicitly requiring a combination of
  traits**" (`6.traits.md:73`) — OAM can say "these two conflict" but not "this one
  needs that one". PACT will need `requires:` as well as `conflicts_with:` (e.g. a
  `computer_use` tool requires a `sandbox` policy, D16).
- **Namespace hazard to avoid:** in KubeVela's Appfile, "there is a restriction that the
  trait type should not conflict any of the Workload parameters' first level name"
  (`config/kubevela/design/vela-core/appfile-design.md:192`) — traits and workload
  params share a flat namespace, so adding a trait can shadow a field. PACT must keep
  resource kinds in their own namespace (`tools:`, `skills:`, `policies:`), never flat.

**The Dhall antidote.** "Every Dhall configuration file can be reduced to a **normal
form** which eliminates all abstraction and indirection"
(`config/dhall-lang/README.md:145-147`), offered explicitly as the answer to the
objection "Configuration languages become unreadable due to abstraction and indirection"
(`:143-147`). Dhall also guarantees "Evaluation always terminates, no exceptions or
crashes. Ever." (`:129-143`) and deliberately impoverishes itself — "you cannot even
compare strings for equality" (`:150-152`).

### 3.2 Recommendation — PACT overlay semantics

**S1. One linear resolution chain, no diamonds.**
`built-in defaults → profile → workspace → agent → variant → run override`.
Six named, ordered layers; **later wins**. No multiple inheritance, no mixins, no
diamond. This is Pkl's amend chain minus the graph, and OAM's ordered trait list.
Rationale: every non-determinism complaint in the corpus (CUE bottom-on-conflicting-defaults,
Jsonnet `super` chains, Helm subchart value precedence) originates in a merge *lattice*
rather than a merge *list*.

**S2. Scalars and maps: replace-by-default; deep merge is opt-in and explicit.**
Follow Jsonnet's default (`language.html.md:479`), reject CUE's unify-by-default.
Opt-in spelled as a field-level directive the author can see:
```yaml
tools:
  merge: append          # replace (default) | append | by_key
```
Never punctuation. Jsonnet's six separators are the counter-example.

**S3. Lists: identity is a `name:` key, never an index.**
Every list element in PACT that can be overridden **must** carry a unique `name:`.
Overlays address elements by name:
```yaml
tools:
  - name: search        # matches base element named "search"
    timeout: 30s
```
Unnamed elements are append-only and non-overridable. Directly counters Pkl's
`[0] { … }` (`index.adoc:1398-1404`) and the "array is replaced during strategic merge
patch" ambiguity (`…gateways.yaml:245`).

**S4. At most one instance of a kind per parent.**
Copy `oam-spec/6.traits.md:67` verbatim in spirit. Two `memory:` blocks on one agent is a
validation error, not a merge.

**S5. Declared conflicts and declared requirements.**
`conflicts_with:` (OAM has it, `6.traits.md:31`) **and** `requires:` (OAM lacks it and
says so, `6.traits.md:73`). Both are declared on the *definition*, checked at load, and
reported with the two-span diagnostic of §2.5.

**S6. No late binding across layers. No lazy cross-references in authored config.**
A value in a PACT file is either a literal or an explicit `${ref:…}` to a *named*
resource — never an expression over sibling fields whose value changes when a sibling is
overridden. This forfeits Pkl's "secret sauce" (`index.adoc:737-780`) on purpose: the
cost of the spreadsheet model is that a git diff stops being a behaviour diff, and D18
surface 4 makes git diff a first-class surface.

**S7. `pact explain` is a required CLI verb, not a nicety.**
Three modes:
- `pact explain agents/researcher` → fully resolved document, all abstraction removed
  (Dhall normal form, `dhall-lang/README.md:145-147`).
- `pact explain agents/researcher --field temperature` → the value **and the layer it
  came from**, with file:line, for every layer that touched it.
- `pact explain --diff` → resolved-form diff between two revisions, so a reviewer sees
  the *behavioural* delta, not the textual one.
Without S7, S1–S6 are still opaque; with it, every overlay question is answerable
offline in one command.

**S8. Defaults live in profiles and are printed.**
Consistent with F-1 ("No hardcoded defaults that cap capability") and AC-7.2. `pact
explain --defaults` lists every default, its value, and the profile that set it.

---

## 4. Control flow without becoming a bad programming language

### 4.1 The Crossplane post-mortem — the single most important document in this corpus

`config/crossplane/design/design-doc-composition-functions.md` is a first-party account
of an organisation that (a) deliberately refused to build a DSL, (b) built one by
accident anyway, and (c) killed it. Every stage is documented.

**The intent** (`:94-120`):
> "Avoid organically growing a new configuration Domain Specific Language (DSL). These
> languages tend to devolve to incoherency as stakeholders push to 'bolt on' new
> functionality to solve pressing problems at the expense of measured design.
> **Terraform's DSL supporting the `count` argument in some places but not others** is a
> great example of this."

> "It was also important to avoid the 'worst of both worlds' — i.e. growing a new, fully
> featured DSL modeled as a REST API. To this end **we omitted common language features
> such as conditionals and iteration.**"

**What happened** (`:132-149`):
> "Folks want to use Composition for more complex cases than we anticipated…"
> "Many Compositions call for a high level of expressiveness — conditionals, iteration,
> merging data from multiple fields, etc."
> "**The lack of a more expressive alternative to P&T Composition _has_ set us down the
> path of organically growing a new DSL.**" — followed by **twelve** issue numbers
> (#1972, #2352, #4051, #3917, #3919, #3989, #3498, #3458, #3316, #4036, #4065, #4026).
> "Organically growing a new DSL is not only undesirable, but **slow**. Because each
> addition to P&T Composition changes Crossplane's core API … Changes take a long time
> to reach consensus. They're coupled to Crossplane's release cycle."

**The resolution** (`:186-196`): `mode: Pipeline` — an ordered array of out-of-tree,
OCI-packaged functions, output of each feeding the next.

**And it stuck.** In current source, patch-and-transform is *gone from the API*:
```go
// +kubebuilder:validation:Enum=Pipeline
// +kubebuilder:default=Pipeline
Mode CompositionMode `json:"mode,omitempty"`
```
— `config/crossplane/apis/apiextensions/v1/composition_types.go:32-41`. The enum has
exactly one member.

**The uncomfortable epilogue.** One of the most popular replacement functions is Go
`text/template` over YAML strings, with `{{- range $i := until (…) }}` loops and
`inline`/`fileSystem` template sources
(`config/crossplane/design/one-pager-function-go-templating.md:38-70`). The escape hatch
became Helm.

**Consequences for PACT, stated plainly.** D14 forbids "experts write code for this".
Crossplane's history says that refusing expressiveness does not prevent a DSL — it
guarantees a *worse* one, accreted under issue pressure, coupled to the core release
cycle. Therefore PACT must:
- Choose its control-flow vocabulary **closed and sufficient on day one**, from
  evidence, not by accretion (§4.3).
- Put the extension point **outside the core release cycle** (out-of-tree, versioned) —
  which PACT already plans for adapters (E-1) and optimizers (E-5), and must extend to
  loop/topology node kinds (G-2, G-3).
- **Never** make the extension point "a string of another language". That is the
  KubeVela `template: |` pattern (§5.3) and the Crossplane go-templating pattern, and it
  is how you get Helm.

### 4.2 What Serverless Workflow proves works — and what it proves does not

**Works:**

1. **A closed 12-verb task vocabulary**: `Call, Do, Emit, For, Fork, Listen, Raise, Run,
   Set, Switch, Try, Wait` (`protocols/serverless-workflow/dsl.md:168-181`). Complete
   enough for the whole comparison matrix in `comparison.md:31-42`, which shows
   retries / timeouts / error handling / parallel / iterative / subflow / conditional
   supported by **all seven** engines compared (Step Functions, Google Workflows, Argo,
   BPMN, Prefect, Dagster). That seven-feature intersection is the empirical floor.

2. **Sequence by declaration order, with explicit override.** "The task to run next is
   **implicitly the next in declaration order**, or explicitly defined by the `then`
   property" (`dsl.md:226`). Zero-ceremony for the common case; the beginner writes a
   list.

3. **Structured jumps only — the anti-spaghetti rule.**
   > "Flow directives may only redirect to tasks declared **within their own scope**. In
   > other words, they cannot target tasks at a different depth."
   > — `dsl.md:230-231`, repeated at `dsl-reference.md:1294-1295`

   Four directives total: `continue`, `exit`, `end`, `<task-name>`
   (`dsl-reference.md:1287-1292`). This is the rule that stops a declarative workflow
   from becoming assembly.

4. **`switch` with an implicit default arm.** "If not set, the case will be matched by
   default if no other case match. Note that there can be **only one** default case, all
   others MUST set a condition." (`dsl-reference.md:1198`).

5. **Priority of Constituencies, written into the spec:**
   > "Authors: people authoring and reading workflows … **If a trade-off needs to be
   > made, always put author's needs above all.** … Author needs come before the needs of
   > operators, which come before the needs of runtime implementors, which come before
   > the needs of specification writers, **which come before theoretical purity**."
   > — `dsl.md:54-67`

**Does not work — the data-flow model:**

The 11-stage data pipeline (`dsl.md:239-283`) exposes **five distinct data planes** the
author must keep straight — raw input, transformed input (`$input`), raw output,
transformed output (`$output`), and workflow context (`$context`) — plus `$secrets`,
`$task`, `$workflow`, `$runtime`, `$authorization`. Availability is a 7×8 matrix
(`dsl.md:451-459`).

**The spec's own flagship multi-agent example demonstrates the failure.**
`protocols/serverless-workflow/use-cases/multi-agent-ai-content-generation/README.md:83-171`
— five AI agents, ~90 lines of YAML:

```yaml
  - initialize:
      set: { prompt: ${ $workflow.input.prompt } }
      export: { as: .prompt }                        # line 87
  - generateText:
      call: http
      …
      export: { as: $context + { text: .text } }     # line 97
```

`export.as` "**replaces** the workflow's current context" (`dsl.md:268`). Line 87 sets
`$context` to the prompt **string**. Line 97 then evaluates `$context + { text: .text }`
— a jq `string + object`, which is a type error. **[inferred]** — I did not execute this;
the inference chains `dsl.md:268` (export replaces context), `README.md:87` (context
becomes a string), `README.md:97` (string is added to an object), and jq's typing rules.
A second problem is visible at `README.md:155-157`: `reevaluate`'s `export.as: .evaluation`
replaces the context with just the evaluation object, and the flow then jumps to
`evaluateQuality`, which reads `${ .text }` and `${ .image }` — no longer reachable.
Third: `refineContent`'s `switch` (`README.md:120-127`) has two conditioned cases and
**no default arm**, so a null `needsRefinement` matches nothing.

**Finding: the working group that wrote the DSL could not write a correct 90-line
multi-agent workflow in it.** That is the strongest available evidence that a
multi-plane, expression-threaded data model is beyond a non-technical author, and it is
directly on PACT's target use case (D20: "a non-technical author builds a multi-agent
system").

### 4.3 What OAM/KubeVela adds

- **"Application Models Are Not Programming Models."**
  > "An application model describes the *composition* of an application and the topology
  > of its components. It is not concerned with *how* each component is implemented …
  > The Open Application Model offers an application model that does not have any
  > requirements of a programming model."
  > — `protocols/oam-spec/9.design_principles.md:29-33`

  Adopt this verbatim as a PACT design principle for the topology/loop IR.

- **"Balance (Elegance): Simple scenarios should be achievable with minimal investment
  of time and energy, but complex scenarios should be accommodated without requiring
  re-platforming."** (`9.design_principles.md:15`) — the precise statement of the
  "one file → full tree" progressive-disclosure requirement (T5, O7.1–O7.3).

- **Three-tier namespace for extensibility:** `core.oam.dev` (runtimes REQUIRED to
  implement), `standard.oam.dev` (RECOMMENDED, portability-maximising), and extension
  namespaces (runtime-specific, MUST NOT use the first two)
  (`6.traits.md:83-87`). PACT's thesis has only *core* and `x-`; **a middle "standard"
  tier is worth adding** — it gives adapters a portability target between "everyone must
  implement" and "nobody has to", which is exactly what a capability lattice (P-2) needs.

- **KubeVela's `if` is the cautionary tale.** Workflow-step conditionals are
  "executed as cue code" with implicit `status` and `inputs` variables
  (`config/kubevela/docs/examples/workflow/app-with-if/README.md:38-44`). Observed
  hazards in a single example file:
  - A magic sentinel mixed into an expression field: `if: always` (`:30`) alongside real
    expressions.
  - **Two spellings for the same thing**: `if: status.suspend.timeout` (`:70`) and
    `if: suspend.timeout` (`:75`) — implicit scope elision.
  - Bracket escape required for hyphenated names: `if: status["notification-1"].succeeded`
    (`:84`).
  - String concatenation smuggled into a data field: `valueFrom: context.name + " message"`
    (`:110`).

  All four are the accretion smell Crossplane warned about.

### 4.4 Recommendation — PACT control flow

**C1. A closed verb set, chosen once.** Derived from the intersection at
`serverless-workflow/comparison.md:31-42` and the 12 verbs at `dsl.md:168-181`, reduced
to what agent orchestration actually needs (G-2 ≥ 8 topologies, G-3 ≥ 6 loops):

| Verb | Purpose | Covers |
|---|---|---|
| `call` | invoke agent / tool / model / sub-team | pipelines, supervisor dispatch |
| `steps` | run children in declaration order | sequential pipeline |
| `parallel` | run children concurrently; `compete: true` for first-wins | map-reduce, debate, best-of-N |
| `each` | iterate a collection; `while:` guard; `max_iterations:` **required** | ReAct, Reflexion, self-consistency |
| `choose` | ordered conditioned arms + exactly one default | routing, handoff, blackboard dispatch |
| `try` | attempt + typed catch + retry policy | fault tolerance |
| `set` | bind a named value into the single data plane | data flow |
| `stop` | terminate this scope with an outcome | halt conditions |

Eight verbs. `wait`, `emit`, `listen` are **not** in the no-code core (they belong to the
runtime seam, D24/D25); if they are needed they enter as `standard`-tier, not `core`.

**C2. `max_iterations` is mandatory on `each`, and there is no `goto`.**
CEL's whole design bets on termination (`cel-spec/README.md:16-17`); Dhall's does too
(`dhall-lang/README.md:143`). A loop IR that can diverge turns "an agent that learns"
into "an agent that burns budget". Every loop is bounded, statically.

**C3. Structured jumps only.** Adopt `serverless-workflow/dsl.md:230-231` verbatim:
a `then:` may only name a sibling in the same scope. Anything else is a validation error
with a two-span diagnostic.

**C4. One data plane.** A single `state` document, plus each step's `result`. No
raw-vs-transformed distinction, no `$context` separate from `$input`, no
availability matrix. Steps read `state.<name>` and write `state.<name>` via `set:` or a
step's declared `output_to:`. This is the direct repudiation of `dsl.md:451-459`.

**C5. Sequence by declaration order.** `steps:` is an ordered array of named tasks; no
edges required for the common case (`dsl.md:226`). Explicit graph edges are an *optional*
expansion for the non-linear topologies (G-2), never required for a pipeline.

**C6. Extension is a *typed node kind*, resolved out-of-tree, never a string of another
language.** A new loop pattern or topology is a `kind:` registered by a definition
package with its own JSON Schema and its own UI hints — the KubeVela definition model
(`design/vela-core/workflow_policy.md:78-95`) minus the CUE-in-a-string, plus the
Crossplane out-of-tree/versioned property (`design-doc-composition-functions.md:181-183`:
"Decouple adding new ways to 'do composition' from the core release cycle"). Escapes to
real code (F-2) remain `ref:`-shaped and *declared*, so they stay analysable — but they
are never the mechanism for expressing a loop.

**C7. Conditions in `choose` and `while` are Tier-0 structured predicates** (§1.6). A
`choose` arm is `{ when: <predicate>, then: <task>, because: <string> }` — which is
byte-for-byte the shape of `cel.policy.Match{condition, output|rule, explanation}`
(`config/cel-spec/proto/cel/policy/policy.proto:47-58`).

---

## 5. YAML vs the alternatives

### 5.1 The constraint set

D2 makes the file tree the native, directly-interpretable form (no build step). D18
requires the *same* files to be written by: (a) a hand editor, (b) a form UI, (c) a
builder agent, (d) reviewed as a git diff. D17 requires everything offline. D4 puts the
loader in Rust.

### 5.2 Scoring the candidates against those constraints

| Candidate | Hand-edit | Form UI round-trip | LLM-generatable | Git diff | Offline | Rust loader | Verdict |
|---|---|---|---|---|---|---|---|
| **YAML (restricted profile)** | ✔ best-known | ✔ if CST-preserving editor | ✔ best-known by far | ✔ line-oriented | ✔ | ⚠ ecosystem gap (§5.4) | **Adopt** |
| JSON | ✔ but noisy; **no comments** | ✔ | ✔ | ✔ | ✔ | ✔ | Interchange only |
| TOML | ✔ flat; poor for deep trees | ✔ | ⚠ | ✔ | ✔ | ✔ | No |
| CUE | ✘ needs unification model | ✘ (KubeVela wraps it, then generates OpenAPI **with a panic-recover**, `pkg/utils/common/common.go:266-289`) | ✘ | ⚠ | ✔ | ✘ (Go) | No |
| KCL | ✘ Python-like, indentation-significant | ⚠ | ⚠ | ⚠ | ✔ | ✔ (is Rust) | No — but **steal its diagnostics** |
| Pkl | ✘ full language | ⚠ | ✘ | ⚠ | ✔ | ✘ (JVM/GraalVM) | No — but **steal its error rendering** |
| Jsonnet | ✘ 6 field separators | ✘ | ✘ | ⚠ | ✔ | ✘ (C++/Go) | No |
| Dhall | ✘ types/lambdas | ✘ | ✘ | ⚠ | ✔ | ✘ (Haskell) | No — but **steal `normal form`** |

### 5.3 The decisive anti-pattern: a second language inside a string literal

KubeVela's extension mechanism is CUE embedded in a YAML block scalar:

```yaml
spec:
  extension:
    template: |
      parameter: {
        cmd: [...string]
      }
      output: { apiVersion: "apps/v1", … }
```
(`config/kubevela/design/vela-core/appfile-design.md:88`, with the rule stated at `:145`:
"The entire template should be put under `spec.extension.template` as **raw string**";
further instances at `:153`, `:314`.)

Costs, all observable:
- No schema validation of the embedded text at the YAML layer; the CUE is opaque to
  every YAML tool.
- Positions inside the block scalar must be re-mapped to be reportable.
- CUE-specific idioms leak into the platform-builder's job: `frequency: *"enabled" |
  "disabled"` (`design/vela-core/workflow_policy.md:90`) is how you write
  "an enum with a default" — unwritable by a non-coder.
- The CUE→OpenAPI→form pipeline is fragile enough to need a `recover()`:
  ```go
  defer func() { if r := recover(); r != nil {
      err = fmt.Errorf("invalid cue definition to generate open api: %v", r) …
  ```
  `config/kubevela/pkg/utils/common/common.go:266-289` (and again at `:292-295`).
- Crossplane arrived at the same anti-pattern from the other direction with Go templates
  in `input.inline.template` (`design/one-pager-function-go-templating.md:18-24`).

**PACT rule: no field in a PACT document may contain source text in another language,
except Markdown (`instructions.md`, skills) and explicitly-typed `ref:` escapes (F-2).**

### 5.4 YAML's real hazards, and the restricted profile that removes them

YAML 1.1 boolean coercion is a live problem, and implementations defend against it
specifically: KCL has a dedicated grammar test whose *entire content* is `on = "on"` and
whose golden output is `'on': 'on'` — quoted on emit
(`config/kcl/tests/grammar/yaml/on/main.k`, `.../stdout.golden`).

**The `pact.dev/v1` YAML profile (normative):**

| Rule | Why |
|---|---|
| YAML **1.2 core schema** only. `y/yes/n/no/on/off` are **strings**, never booleans | KCL's `on` test; the Norway problem |
| **No tabs.** Two-space indent. Emitted canonically | KCL ships tab/indent error tests (`tests/grammar/syntax/tab/tab_error_{0,1}`, `syntax/indent/indent_error_{0,1}`) |
| **No anchors/aliases (`&`/`*`), no merge keys (`<<`)** | Non-local reads; defeats "the file is what runs"; PACT has `$ref`-by-name instead |
| **No multi-document streams (`---`)** per file | One file = one node; the Expansion Rule (T5) already gives multi-node structure via directories |
| **No flow style** for authored content (block style only) | Line-oriented diffs (D18) |
| **No implicit sexagesimal / octal / large-int surprises**; durations and sizes are **suffixed strings** (`30s`, `128k`, `4MB`) with a PACT-owned parser | Same class of coercion bug; also makes `context >= 128k` renderable in a form |
| **Keys are `snake_case`, ASCII, `[a-z][a-z0-9_]*`** | No quoting needed; no `status["notification-1"]` bracket escapes (KubeVela `app-with-if/README.md:84`) |
| **Ordered ⇒ array of records with `name:`. Unordered ⇒ map.** Never a list of single-key maps | `config/kubevela/apis/core.oam.dev/common/types.go:363` ("the type must be array to keep the order"); avoids Serverless Workflow's `- taskName: {…}` double-nesting (`dsl-reference.md:1136-1146`) |
| **Reject duplicate keys** (error, not last-wins) | Silent loss; violates T7/AC-7.1 |
| **Reject unknown keys** with did-you-mean; `x-` prefixed keys round-trip untouched | AC-1.3; OAM's extension-namespace discipline (`6.traits.md:83-87`) |
| Files end with newline; canonical emitter is idempotent (`pact fmt` is a fixed point) | Machine writes must not churn diffs |

### 5.5 The Rust ecosystem gap — a concrete, actionable risk

D18 requires the UI and the builder agent to **write the same files a human hand-edits**.
That requires a **comment- and format-preserving** YAML editor (CST-level), not a
serde-style loader.

Evidence of the gap, from the corpus: KCL — itself a Rust project — **vendors a fork of
`serde_yaml`** at `config/kcl/3rdparty/serde_yaml`, wired in at
`config/kcl/Cargo.toml:44` (`serde_yaml = { path = "3rdparty/serde_yaml" }`). Upstream
`serde_yaml`'s own README states *"(This project is no longer maintained.)"*
(`config/kcl/3rdparty/serde_yaml/README.md:10`), and KCL's note says they "forked the
deprecated upstream serde_yaml library and fixed several critical bugs"
(`README.md:14-16`). A grep for `comment` across `3rdparty/serde_yaml/src/**` returns
nothing — it is comment-lossy by construction.

**Recommendation:** PACT's Rust core needs **two** YAML paths:
1. A **CST/lossless path** (positions, comments, blank lines, key order preserved) used
   by the loader for diagnostics and by *every writer* (UI, builder agent, `pact fmt`,
   learning write-backs under T6/D22).
2. A **value path** for canonicalisation into `canonical.json`.

Round-trip must be a tested invariant: `write(read(f)) == f` byte-for-byte for any
conforming file. Without it, the UI surface silently strips the comments a domain expert
wrote to explain their own agent — and D18 collapses to "files or UI, pick one".

### 5.6 Markdown's role

Keep Markdown strictly for **prose that the model consumes**: `instructions.md`, skills,
eval rubric text, `because:` long-form. It must never carry structure PACT parses beyond
optional YAML front-matter. Rationale: Markdown has no error positions worth reporting
and no schema; structure in Markdown is structure you cannot validate.

---

## 6. The schema→form pipeline (D18, surface b)

KubeVela is the only system in the corpus that ships this end-to-end, and its data model
is the specification PACT should copy.

**Generation:** CUE `parameter` block → OpenAPI v3 → form
(`design/vela-core/appfile-design.md:255`: "For UI, The definition in a template will
be used to generate v3 OpenAPI Schema and the UI will use that to render forms";
implementation `pkg/utils/common/common.go:266-289`, `openapi.Config{ExpandReferences:
true}`).

**Default widget derivation** (`pkg/utils/schema/ui_schema.go:128-155`) — this maps
straight onto PACT's JSON Schema and needs no per-field authoring:

| JSON Schema | Widget |
|---|---|
| `string` | `Input` (`Select` when `enum` present) |
| `number` / `integer` | `Number` |
| `boolean` | `Switch` |
| `array<string>` | `Strings` |
| `array<number\|integer>` | `Numbers` |
| `array<other>` | `Structs` |
| `object` with properties | `Group` |
| `object` without properties | `KV` |

**What JSON Schema cannot express, and therefore what PACT must carry alongside it**
(`pkg/utils/schema/ui_schema.go:42-125`):

| Field | Why JSON Schema is insufficient |
|---|---|
| `Sort uint` (`:44`) | JSON Schema objects are unordered; forms are not |
| `Label` (`:45`) | Human name ≠ `jsonKey` |
| `Description` (`:46`) | (JSON Schema has `description`, but not per-surface) |
| `UIType` (`:49`) | Widget override |
| `Style.ColSpan` (`:50,96-99`) | Layout |
| `Disable` (`:52`) | Progressive disclosure |
| `Conditions []Condition` (`:60`) | Show/hide by another field's value: `{jsonKey, op ∈ {==,!=,in}, value, action ∈ {enable,disable}}` (`:68-79`), with documented precedence at `:53-58` and validation at `:82-93` |
| `SubParameterGroupOption` (`:61,102-105`) | Which `oneOf` branch, as a labelled choice |
| `Validate.Immutable` (`:118`) | "cannot be changed twice" — no JSON Schema equivalent |
| `Validate.Options []Option{Label,Value}` (`:115,122-125`) | Enums need **display labels**, not just values |

**Recommendation.** PACT ships, per schema node, an optional `x-pact-ui` block carrying
exactly these: `sort`, `label`, `help`, `widget`, `group`, `show_when` (a Tier-0
structured predicate — same construct as §1.6, so one predicate model serves routing,
evals *and* forms), `immutable`, and `options: [{label, value}]`. Everything else is
derived from JSON Schema via the table above. This keeps the form UI a *pure function of
the schema plus a thin hint layer* — the property that makes E-3 ("new authoring surface
is free") true for the UI as well as the filesystem.

---

## 7. Cross-cutting: what "no-code" costs, measured

| Concern | Evidence of the cost | PACT mitigation |
|---|---|---|
| Hand-translating another format into the config language is error-prone | KubeVela on its own addons: "This is **hugely error prone** as the CRDs etc. are converted to cue … Addons are not always kept up to date" (`design/vela-core/helm-component.md:28-32`) | D15 ("translate or nothing") is expensive — invest in *mechanical* importers with `ImportReport` (P-3), never hand-ported definitions |
| Expression syntax in user data is an injection vector | "Runtimes must not parse or evaluate expression syntax embedded in workflow input" (`serverless-workflow/dsl.md:385-386`) | Tier-0 predicates are data; Tier-1 CEL evaluates only text from spec files, never from run inputs |
| Errors truncated by default | `cue/parser/interface.go:132-133`, `cmd/cue/cmd/flags.go:104` | Report all, always |
| Rule provenance invisible | CUE's `field not allowed` with no "says who" | Two-span diagnostics (§2.5) |
| Overlay effects non-local | Pkl spreadsheet semantics (`index.adoc:770-776`) | No late binding (S6) + `pact explain` (S7) |
| Docs drift from behaviour | OPA's `# METADATA` model attaches title/description/authors/related_resources to rules with scope inheritance (`config/opa/v1/ast/annotations.go:20-90`: scopes `package\|rule\|document\|subpackages`, resolved through an `annotationTreeNode`) | PACT's `because:`/`description:` are *fields of the rule*, not comments, and inherit down the tree the same way |

---

## 8. Concrete spec-ready decisions (summary of §1–§6)

1. **No author-facing expression language.** Tier-0 structured predicates
   (`{atom, operator, value}` lists, implicit AND; `all_of`/`any_of`/`none_of`
   combinators) are the complete no-code surface for capability requirements, routing,
   eval gates, SLO gates and form conditionals.
2. **Tier-1 restricted CEL** as an optional expert form: macros/arithmetic/string-ops
   disabled, `&&`/`||` lowered to `?:`, all numerics `double`, must round-trip to Tier 0
   where expressible. Gated by the CEL conformance textproto suite offline.
3. **Every predicate carries `because:`** (mandatory). Every arm of a `choose` is
   `{when, then, because}` = `cel.policy.Match{condition, output, explanation}`.
4. **JSON Schema for shape only**; PACT owns a **stable-coded error catalogue** shipped
   as in-repo Markdown, with two spans, inlined actual value, did-you-mean, and a
   one-line fix. All errors, every run.
5. **Discriminator-first validation** — never expose `oneOf` failures.
6. **Six-layer linear overlay**, replace-by-default, explicit `merge:`, name-keyed lists,
   one instance per kind, `conflicts_with:` **and** `requires:`, no late binding.
7. **`pact explain`** (normal form / field provenance / resolved diff) is a required CLI
   verb.
8. **Eight control-flow verbs**, declaration-order sequencing, bounded loops,
   scope-local jumps only, single data plane, out-of-tree typed node kinds for
   extension — never another language in a string.
9. **YAML 1.2 restricted profile** (no tabs/anchors/aliases/merge-keys/multi-doc/flow;
   1.2 core schema; snake_case keys; suffixed durations and sizes; duplicate keys are
   errors; `x-` round-trips).
10. **Lossless CST YAML I/O in the Rust core**, with `write(read(f)) == f` as a tested
    invariant — the Rust ecosystem does not supply this off the shelf.
11. **`x-pact-ui` hint layer** (sort/label/help/widget/group/show_when/immutable/options)
    so the form UI is a pure function of schema + hints.
12. **Add a `standard`-tier namespace** between core and `x-` extensions
    (OAM's three-tier model), giving adapters a portability target.

---

## 9. Open questions (for the architecture pass)

1. **Which Rust CEL?** No Rust CEL implementation appears in the local corpus. If Tier 1
   ships, does PACT vendor a Rust CEL, run an out-of-process evaluator (breaking the
   "core has no service dependency" property in-process but not off-machine), or define
   its own tiny evaluator over the restricted profile? The last is ~500 lines and removes
   the protobuf-AST dependency entirely — but forfeits the conformance suite as a gate.
2. **Does Tier 0 actually cover D14's ceiling?** Needs a falsification pass: take the 6
   loop patterns (AC-5.2) and 8 topologies (AC-5.1) and try to write every `when:` in
   Tier 0. Any pattern that needs arithmetic or aggregation (e.g. "majority vote of N
   verifiers") is a candidate for a *named atom* (`majority_of:`) rather than an
   expression.
3. **Where do SLO predicates live?** `TTFT p95 < 300ms` is a Tier-0 atom, but percentile
   semantics (O4.2) and modality-awareness (D16: voice TTFT ≠ batch E2E) mean the atom
   needs a `percentile:` and a `modality:` field. Is that one atom kind or several?
4. **Merge semantics for `instructions.md`.** The Expansion Rule makes a Markdown file a
   field value. Do overlays *replace* the file, or is there an append/prepend? Eve's
   answer was "copy the markdown under each `skills/`" (thesis §1.3), which the thesis
   calls out as a defect. Replace-by-default (S2) is the consistent answer, but skills
   composition may want append — needs a decision.
5. **Do `x-` blocks participate in overlay?** They must round-trip (AC-1.3) but if two
   layers both set `x-vendor.foo`, PACT does not know the merge semantics. Proposal:
   `x-` blocks are always replaced wholesale at the owning key, never deep-merged.
6. **Error-catalogue localisation.** Pkl externalises 1,210 message strings for exactly
   this reason. Does PACT commit to a `.properties`-style catalogue from day one, or
   inline English and refactor later? (Inlining is cheaper now and much more expensive
   at ~200 messages.)
7. **`pact explain --diff` and the change-classification function (D23).** The
   blast-radius classifier operates on spec diffs. Should it operate on the *authored*
   diff or the *resolved* diff? Resolved is semantically correct but produces enormous
   diffs; authored is reviewable but can miss overlay-mediated behaviour changes. S7's
   resolved-diff mode is the input the classifier probably wants.
8. **oam-spec is dormant** (last commit 2024-12-24). Borrowing its three-tier namespace
   and trait rules is fine — borrowing its *governance* as a portability argument is not.
