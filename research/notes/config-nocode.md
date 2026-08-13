# Research stream: `config-nocode`

**Question owned:** what makes declarative configuration usable — or unusable — by a
non-technical domain expert (D13) who must nonetheless build a *complete* multi-agent
system with custom tools, evals, SLOs and learning **in YAML/Markdown alone** (D14),
**fully offline** (D17), across **four author surfaces** (D18), where the **file tree is
the native form** (D2).

**Corpus read (source, not READMEs):**
`research/repos/config/{cel-spec,cue,kcl,pkl,jsonnet,dhall-lang,opa,kubevela,crossplane}`,
`research/repos/protocols/{json-schema-spec,serverless-workflow,oam-spec}`,
plus — added this pass, because the corpus contains no standalone Helm/Kustomize repo but
does contain real charts and overlays —
`research/repos/routing/litellm/helm/`, `research/repos/eval/phoenix/kustomize/`,
`research/repos/eval/promptfoo/helm/`, and — for routing predicates specifically —
`research/repos/routing/portkey-gateway/src/services/conditionalRouter.ts` and
`research/repos/routing/litellm/litellm/types/router.py`.

**Evidence discipline.** Every claim carries `path:line`. Paths are relative to
`/home/bud/ditto/agent-inter-op/research/repos/` unless absolute. Claims I did not
execute are marked **[inferred]**. Claims I *did* execute are marked **[executed]** and
the reproduction script is in Appendix A — every one of them runs offline against the
local corpus.

**Repo freshness** (`git log -1`, checked this pass): cue 2026-07-24, kcl 2026-07-24,
pkl 2026-07-25, opa 2026-07-25, kubevela 2026-07-22, crossplane 2026-07-24, cel-spec
2026-07-20, dhall-lang 2026-07-19, jsonnet 2026-03-30, serverless-workflow 2026-07-23,
json-schema-spec 2026-07-14, **oam-spec 2024-12-24 (dormant ~20 months)**.

**What is new in this pass** (vs. the 2026-07-26 revision of this note):

| # | New result | Kind |
|---|---|---|
| N1 | The Serverless Workflow spec's flagship multi-agent AI example **is not valid YAML**. Verified by parsing it. | [executed] |
| N2 | A **one-character typo** in a valid 24-line Serverless Workflow document produces **65 error units** from a conformant JSON Schema 2020-12 validator, none of which say "did you mean `call`". | [executed] |
| N3 | `unevaluatedProperties: false` **converts a wrong *value* into a false "unknown *field*" error** — by spec, not by implementation bug. Causal chain traced through three normative clauses. | [executed] + spec |
| N4 | JSON Schema `default` is an annotation with **no validity requirement and no conflict-resolution rule**. Defaults must not live in the schema. | spec |
| N5 | The spec writes expression fields **four different ways** across its own examples (6 / 6 / 40 / 23 occurrences). Two of the spellings break the host YAML parser. | [executed] |
| N6 | Portkey's shipping conditional-router is a Tier-0 structured predicate with **11 operators** — and contains four silent-wrong-answer bugs that PACT must specify away, including `missing data ⇒ predicate false`. | source |
| N7 | KCL ships **author-written check messages** with two-span rendering — the closest thing in the corpus to PACT's mandatory `because:`. And the message-less variant proves why it must be mandatory. | source |
| N8 | OPA ships a **runtime did-you-mean over data** (`levenshtein ≤ 3`) that explains *why a rule was undefined* — the exact shape D11's "fail, then recommend" needs. | source |
| N9 | Measured cost of templated config: the LiteLLM chart is **839 template lines, 61% containing `{{`, and 1,434 lines of unit tests** — a 1.71:1 test-to-template ratio. | [executed] |
| N10 | The Phoenix Kustomize overlay's behaviour **cannot be determined from the two files that constitute it**. Merge semantics are declared nowhere in the tree. | source |
| N11 | Serverless Workflow has **no mandatory termination bound anywhere**: `while` uncapped, `retry.limit` optional, and its own example contains an unbounded refinement cycle. | source |

---

## 0. Executive verdict (the five answers)

| # | Question | Verdict |
|---|---|---|
| 1 | Does PACT need an expression language? | **No, not on the no-code path.** Ship **structured predicates** (typed atoms, implicit AND) as the *only* form a non-coder ever writes. Add a **restricted CEL profile** as an *expert-tier, optional* escape that desugars *from* structured predicates and is always displayed back as structured predicates. Two independent shipping systems converge on the same ~11-operator set from opposite directions — Crossplane for *validation* (50 CEL rules), Portkey for *routing* (11 operators). That convergence, not theory, is the evidence. |
| 2 | Validation strategy for actionable errors | JSON Schema for **shape only**, PACT-owned **rule catalogue** for **messages**, and **key-checking must be a separate pass** — never `additionalProperties`/`unevaluatedProperties`, which measurably produce *false* diagnoses (N3) and 65-unit error storms (N2). Copy KCL (stable code + two spans + inlined value + did-you-mean) and Pkl (sub-expression value trace), and copy OPA's `failtracer` for "why did nothing match". |
| 3 | Defaulting / inheritance / overlay | **One linear amend chain, replace-by-default, explicit `merge:` opt-in, key-based (never index-based) list identity, at most one instance of a kind per parent** — and **defaults live in profiles, never in the JSON Schema** (N4). Reject unification-style defaults. Ship `pact explain <path>` as the antidote to non-locality. The overlay must be *readable from the files that constitute it* — the Kustomize failure (N10) is that it is not. |
| 4 | Control flow without becoming a bad language | A **closed 8-verb task vocabulary**, sequence-by-declaration-order, **structured-only jumps**, **mandatory termination bounds**, **mandatory default arm**, and a **single data plane**. Crossplane's post-mortem says refusing expressiveness produces a *worse* accreted DSL; Serverless Workflow's own flagship example — unparseable, with three data-flow bugs and an unbounded loop — says a multi-plane expression-threaded model is beyond its own authors, let alone a support lead. |
| 5 | YAML vs alternatives | **YAML 1.2 core schema, restricted profile, as the only author-facing syntax.** No embedded second language in string literals — now upgraded from "anti-pattern" to "provably breaks the host parser" (N1/N5). PACT's Rust core needs a comment/format-preserving CST YAML editor, because the dominant Rust crate is unmaintained and comment-lossy. |

---

## 1. Expression languages

### 1.1 What the corpus actually uses

| System | Expression language | Where it appears | Read from |
|---|---|---|---|
| Crossplane | **CEL** (`XValidation`) | **50** rules, **50/50 carrying `message=`** | `config/crossplane/apis/**/*_types.go` |
| Kubernetes/KubeVela | **CEL** (CRD validation) + **CUE** (templates) + **CUE-as-`if`-string** (workflow steps) | three different languages in one product | `config/kubevela/design/vela-core/appfile-design.md:74`, `config/kubevela/docs/examples/workflow/app-with-if/README.md:38` |
| Serverless Workflow | **jq**, mandatory; others optional via `evaluate.language` | every task | `protocols/serverless-workflow/dsl.md:379` |
| OPA | **Rego** | whole product | `config/opa/v1/ast/` |
| CUE | **CUE itself** | whole product | `config/cue/doc/ref/spec.md` |
| Pkl | **Pkl itself** (`Int(this >= min)`) | whole product | `config/pkl/pkl-core/src/test/files/LanguageSnippetTests/output/classes/constraints5.err` |
| **Portkey Gateway** | **structured operator objects — 11 operators, no parser** | LLM request routing | `routing/portkey-gateway/src/services/conditionalRouter.ts:15-30` |
| **LiteLLM** | **no language — a 4-value closed enum** | LLM request routing | `routing/litellm/litellm/types/router.py:84-89` |
| KubeVela UI layer | **3 operators only** (`==`, `!=`, `in`) | form field enable/disable | `config/kubevela/pkg/utils/schema/ui_schema.go:71-79`, enforced at `:82-93` |
| Kubernetes label selectors | **no language** — `{key, operator, values}` atoms, "requirements are ANDed" | selectors everywhere | CRD text at `config/kubevela/pkg/workflow/providers/legacy/query/testdata/gateway/crds/gateway.networking.k8s.io_gateways.yaml:222-247` |

The two rows that matter most for PACT are the two *routing* rows, because routing
predicates are the one place where PACT genuinely needs to select among alternatives at
run time, and both shipping LLM routers solve it **without an expression language**.

### 1.2 The routing evidence — Portkey's conditional router, read in full

`routing/portkey-gateway/src/services/conditionalRouter.ts` is 156 lines and is the
complete, shipping predicate language for a production LLM gateway.

**The operator set is closed and small** (`:15-30`):

```
comparison : $eq  $ne  $gt  $gte  $lt  $lte  $in  $nin  $regex
logical    : $and $or
```

Eleven operators. No arithmetic, no string construction, no comprehensions, no macros,
no user-defined functions, no interpolation. The predicate is a **JSON object**, so it
has no grammar, no lexer, no injection surface, and it renders as a form for free.

**The control shape is exactly what PACT's `choose` wants** (`:49-62`):

```ts
for (const condition of this.config.strategy.conditions) {
  if (this.evaluateQuery(condition.query)) { return this.findTarget(condition.then); }
}
if (this.config.strategy.default) { return this.findTarget(this.config.strategy.default); }
throw new Error('Query router did not resolve to any valid target');
```

Ordered arms of `{query, then}`, an explicit `default`, and — importantly — a **hard
failure when nothing matches and no default exists** (`:61`). Compare Serverless
Workflow, where the same situation silently falls through to the next declared task
(§4.2).

**Now the four bugs, because each one is a rule PACT must write into the spec:**

1. **Sibling logical operators silently discard their siblings.** `evaluateQuery`
   *returns* on the first `$or`/`$and` key it meets (`:66-76`):
   ```ts
   if (key === Operator.Or && Array.isArray(value)) {
     return value.some((subCondition) => this.evaluateQuery(subCondition));
   }
   ```
   So `{ $or: [...], "metadata.tier": "gold" }` evaluates the `$or` and **never looks at
   `metadata.tier`**. The document reads as a conjunction; the code is not one.
   ⇒ **PACT rule:** a predicate node is *either* a combinator *or* an atom, structurally,
   never both. `all_of`/`any_of`/`none_of` are the only keys allowed in a combinator node.

2. **Missing data is indistinguishable from a failed comparison.** `$gt` is
   `parseFloat(value) > parseFloat(compareValue)` (`:102`). If the field is absent,
   `parseFloat(undefined)` is `NaN`, and every comparison against `NaN` is `false`.
   ⇒ This is *precisely* the `MMLU > 80` case. A model whose MMLU figure is simply
   **absent from the catalogue** silently fails the predicate, and the author is told the
   model does not meet the bar rather than that the bar could not be checked. That is a
   direct violation of T7 (structural honesty) and of AC-3.3 (provenance-gated figures).
   ⇒ **PACT rule:** predicate evaluation is **three-valued** — `pass | fail | unknown`.
   `unknown` (figure absent, or absent provenance in `strict` mode) is never silently
   coerced to `fail`; it produces its own diagnostic and its own line in the Portability
   Report.

3. **Path traversal is silently truncated to two segments** (`:150-155`):
   ```ts
   const parts = key.split('.');
   value = value[parts[0]]?.[parts[1]];
   ```
   `a.b.c` reads `a.b` and drops `.c`; a single-segment key reads `obj[undefined]`.
   Both yield `undefined` ⇒ `false` (see bug 2).
   ⇒ **PACT rule:** every reference in a predicate resolves against a **declared name
   set** at load time, and an unresolvable reference is a load error with a did-you-mean,
   never a run-time `undefined`.

4. **`$regex` returns instead of breaking, and swallows its own compile error**
   (`:121-127`): a malformed regex returns `false` from the `catch`. A typo in a pattern
   is indistinguishable from a non-match.
   ⇒ **PACT rule:** any operator that can fail to *compile* is validated at load time.

**And the meta-finding, which is the most important one in this section:** the router's
own config schema does **not validate the predicate at all**:

```ts
conditions: z.array(z.object({ query: z.object({}), then: z.string() })).optional(),
default: z.string().optional(),
```
— `routing/portkey-gateway/src/middlewares/requestValidator/schema/config.ts:29-37`

`query: z.object({})` accepts any object. So `$gte` misspelled as `$gt3` passes config
validation and throws at request time (`conditionalRouter.ts:128-131`), and a conditional
config with **no `default`** validates cleanly and throws on the first unmatched request
(`:61`).

Meanwhile the *scalar* fields in the same file all carry good hand-written messages —
`"Invalid 'mode' value. Must be one of: single, loadbalance, fallback, conditional"`
(`config.ts:24-26`), `"Invalid 'provider' value. Must be one of: …"` (`:42-45`),
`"'retry.attempts' must be defined"` (`:72`).

> **The lesson:** a team that writes good enum messages still leaves the predicate
> sub-language entirely unvalidated, because validating a nested expression object
> requires a schema *for the expression language*, and nobody writes one. The moment a
> predicate becomes "just an object", validation stops. **PACT's structured predicates
> must be first-class typed schema nodes with their own closed key sets, or they will
> get the same treatment.**

**LiteLLM corroborates from the other end**: its `routing_strategy` is a four-member
`Literal` — `simple-shuffle | least-busy | usage-based-routing | latency-based-routing`
(`routing/litellm/litellm/types/router.py:84-89`). Not a predicate at all: a closed
choice. Two production LLM routers, neither of which needs a language.

### 1.3 The CEL evidence, re-verified

**What CEL gets right (verified in spec, line numbers current):**
- Grammar is ~26 lines of BNF (`config/cel-spec/doc/langdef.md:26-52`).
- "memory-safe … side-effect-free … **terminating** … strongly-typed … gradually-typed"
  (`langdef.md:8-19`); "evaluates in linear time, is mutation free, and **not
  Turing-complete**" (`config/cel-spec/README.md:16-20`).
- Per-AST-node source positions exist (`proto/cel/expr/syntax.proto:354-356`) and macro
  expansions back-map to their original call (`syntax.proto:358-365`).
- Implementations may cap or **disable macros entirely** (`langdef.md:901`).
- **CEL has a policy format with `explanation` per match arm** — verified:
  ```proto
  message Match {
    optional string condition = 1;
    oneof action { string output = 2; Rule rule = 3; }
    string explanation = 4;
  }
  ```
  `config/cel-spec/proto/cel/policy/policy.proto:47-59`. This remains the single most
  directly copyable artifact in the corpus for PACT's `choose` arm.
- **An offline conformance gate exists**: 30 textproto files, **2,855 test cases**, in
  `config/cel-spec/tests/simple/testdata/` — usable air-gapped (D17) to certify any Tier-1
  implementation PACT writes. [executed: `ls *.textproto | wc -l` → 30;
  `grep -h "^ *name:" *.textproto | wc -l` → 2855]

**What CEL gets wrong for a non-coder (all re-verified this pass):**

1. **Only two runtime errors exist.** `no_matching_overload` and `no_such_field`
   (`langdef.md:648-650`); "no way to catch or bypass errors" (`langdef.md:653`). A
   failing predicate returns **`false`**, with no account of which conjunct failed or what
   the value was.
2. **The "explain" mechanism is deprecated upstream.** `proto/cel/expr/explain.proto:28`
   — `option deprecated = true;` on the entire `Explain` message. ⇒ **PACT would have to
   build its own sub-expression value tracer.**
3. **`MMLU > 80` — the exact PACT example — is a type error in strict CEL.**
   "Comparisons require strict type equality at type-check time" (`langdef.md:1532`);
   "The one exception … is numeric comparisons at runtime" (`:1536-1539`). The conformance
   suite writes **every** cross-type comparison as `dyn(...)`:
   `dyn(1) == 1u`, `dyn(1) == 1.0`, `dyn(2) > 1.0` … (`tests/simple/testdata/comparisons.textproto:21-66`),
   and unsupported comparisons need `disable_check: true` and yield `no such overload`
   (`comparisons.textproto:1203-1215`). If the catalogue declares `MMLU: double` and the
   author types `> 80`, a type-checked environment rejects it with **`no such overload`**
   — the worst possible message for a support lead. Mitigable (all catalogue numerics
   `double`, integer literals promoted at compile time) but only *consciously*.
4. **`&&` / `||` are commutative, not short-circuiting.** "This makes those operators
   commutative" and errors in the non-determining operand "will be ignored"
   (`langdef.md:661-668`). To get McCarthy evaluation you must rewrite `e1 && e2` as
   `e1 ? e2 : false` (`langdef.md:671-672`). The forgiving behaviour **silently swallows
   errors** — hostile to T7 and D11.
5. **Order of error propagation is unspecified** (`langdef.md:604-608`) — a conformance
   hazard for out-of-tree adapters in three languages (D4).
6. **17 reserved words that look like ordinary field names** (`langdef.md:137-149`):
   `as break const continue else for function if import let loop package namespace return
   var void while`. A PACT capability named `import` or `function` would be unusable
   inside an expression.
7. **CEL's own stated audience is developers**: "The language is approachable **to
   developers**" (`config/cel-spec/README.md:25-27`).

**And, still true after a full re-check of the corpus: there is no Rust CEL
implementation anywhere in the 141 repos.** [executed: `grep -rl "cel-interpreter|cel_interpreter|cel-parser" repos/ --include=Cargo.toml` → empty]

### 1.4 The empirical minimum — two independent derivations that agree

**Derivation A — validation (Crossplane, 50 CEL rules).** The *entire* construct set used
across the API:

```
has(x)      self == oldSelf      !(a && b)
a && b      a || b      !a       a == b      a != b
size(self) > 0           self.plural == self.plural.lowerAscii()
```
Sources: `config/crossplane/apis/apiextensions/v1/xrd_types.go:39-52`,
`apis/apiextensions/v1/composition_types.go:25,29`,
`apis/protection/v1beta1/usage_types.go:121-130`,
`apis/pkg/v1beta1/image_config_types.go:76`,
`apis/apiextensions/v1alpha1/mrd_types.go:36`.

**Every one of the 50 rules carries an author-written `message=` in plain English.**
[executed: `grep -rn XValidation crossplane/apis/ | wc -l` → 50; `| grep -c "message="`
→ 50.] Verbatim samples:
`"an array of pipeline steps is required in Pipeline mode"`,
`"name and matchLabels are mutually exclusive"`,
`"either a resource reference or a resource selector should be set."`,
`"state cannot be changed once it becomes Active"`,
`"Plural name must be lowercase"`, `"the Secret source requires a secretRef"`,
`"cross-namespace \"spec.of\" is not allowed without \"spec.by\" resource."`.

**Derivation B — routing (Portkey, production LLM gateway).** Eleven operators
(`conditionalRouter.ts:15-30`), no arithmetic, no interpolation.

**The two sets are nearly identical**, and were arrived at by different teams solving
different problems. Zero arithmetic, zero comprehensions, zero macros, zero string
interpolation in either. **That is the size of the expression language PACT actually
needs, and it is small enough to be a data structure rather than a grammar.**

Third corroboration, from the UI tier: KubeVela's form-conditional language is exactly
**three** operators — `==`, `!=`, `in` — with an explicit allowlist
(`config/kubevela/pkg/utils/schema/ui_schema.go:71-79`, validated at `:82-93`).
Fourth, from Kubernetes: `matchExpressions` is `{key, operator ∈ {In, NotIn, Exists,
DoesNotExist}, values[]}` with "**The requirements are ANDed**" — a zero-parser predicate
language that has survived a decade at planetary scale.

### 1.5 jq (Serverless Workflow) is disqualified — now with executed evidence

- Mandated as the default and only guaranteed language (`protocols/serverless-workflow/dsl.md:379`).
- **The spec is inconsistent about delimiters in four distinct ways.** [executed, Appendix
  A.3] Across `dsl.md`, `dsl-reference.md`, `examples/*.yaml`, `use-cases/**` and
  `ctk/features/*.feature`, expression-bearing fields (`when while until as from in if
  condition set`) are written:

  | Spelling | Occurrences | Example |
  |---|---:|---|
  | `${ … }` unquoted | 6 | `dsl-reference.md:952` `from: ${ .message }` |
  | `'${ … }'` quoted | 6 | `dsl-reference.md:2721` `until: '${ ($context.messages \| length) == 5 }'` |
  | bare `.expr` | **40** | `dsl-reference.md:708` `in: .pets` |
  | quoted `'.expr'` | 23 | `dsl-reference.md:225` `as: "$input + { availablePets: … }"` |

  Strict mode says "all expressions must be properly identified with `${}` syntax"
  (`dsl.md:375`), and yet the **most common form in the spec's own examples is the bare
  one**, by a factor of nearly seven. A non-coder cannot infer the rule because the rule
  is not followed.
- **Two of those spellings are not valid YAML.** See §5.3 / N1 — this is no longer an
  aesthetic objection.
- Expression-argument availability is a **7×8 matrix** the author must memorise
  (`dsl.md:451-459`): `$output` is available in `export.as` but not `output.as`;
  `$secrets` only in workflow `input.from`; `$authorization` only after the task-definition
  stage.
- jq's `.` context re-binds at every one of the 11 data-flow stages (`dsl.md:239-283`), so
  the *same expression text* means different things in different fields. This is not
  hypothetical: it is what broke the spec's own multi-agent example (§4.2).

### 1.6 CUE / Pkl / Rego as the predicate language — rejected

- **CUE**: the semantics needed to reason about a default are 10 rewrite rules
  (`config/cue/doc/ref/spec.md:783-804`) plus a subsumption lattice (`:825-832`), and the
  canonical failure `(*1|2) & (1|*2) ⇒ ⟨1|2, _|_⟩` (`spec.md:820`) means **two layers each
  declaring a different default for one field is a hard error, not a resolution.** Writing
  a constraint with a message requires `x: int | error("I wanted an integer")`
  (`config/cue/cue/testdata/builtins/error.txtar:81`).
- **Pkl**: constraint syntax is `Int(this >= min)` — a type with an embedded predicate.
  Best-in-corpus error rendering (§2.4), but a full functional language with classes,
  `amends`, late binding, `local`/`fixed`/`const`/`hidden`, and JVM/GraalVM runtime weight.
- **Rego**: canonical error is `var x is unsafe` (`config/opa/v1/ast/compile.go:1619,7343`).
  OPA itself acknowledges the opacity by bolting a case-specific hint onto one instance:
  `"var %[1]v is unsafe (hint: \`import future.keywords.%[1]v\` …)"` (`compile.go:7340`).
  Datalog semantics are further from a support lead's mental model than any other
  candidate. (But OPA's *hint machinery* is worth stealing wholesale — §2.5.)

### 1.7 Recommendation — the two-tier predicate model

**Tier 0 (the only no-code surface): structured predicates.** A predicate is a *list of
typed atoms*, implicitly AND-ed, each a small closed record.
`MMLU > 80 && SWE-Verified > 40 && context >= 128k` becomes:

```yaml
requires:
  - benchmark: MMLU
    at_least: 80
    because: "the agent must handle general-knowledge questions unaided"
  - benchmark: SWE-Verified
    at_least: 40
    because: "it edits code in the repo"
  - context_window:
      at_least: 128k
  - capability: tool_calling
    mode: parallel
```

Properties, each traceable to evidence:
- **No parser, no injection surface.** Satisfies the Serverless Workflow security
  requirement verbatim: "Runtimes **must not** parse or evaluate expression syntax embedded
  in workflow input or task input data … exposes the system to injection attacks"
  (`dsl.md:387`).
- **Per-atom failure messages are mechanical**: `MMLU is 74.1 for qwen3-4b; you require at
  least 80` — no tracing machinery, which matters because CEL's is deprecated
  (`explain.proto:28`).
- **Three-valued by construction** (from Portkey bug 2): the atom knows whether the figure
  was *absent*, so `unknown` is expressible. An expression language cannot distinguish
  `absent` from `false` without extra machinery.
- **Forms render for free**: each atom is one row; the operator is a `Select` from a closed
  enum — exactly KubeVela's `GetDefaultUIType` mapping (`ui_schema.go:128-155`).
- **Diffs are line-oriented** (D18): changing a threshold changes one line.
- **Builder agents emit it reliably** — JSON-shaped data, not a string to be lexed.
- **No cross-type comparison trap**: `at_least: 80` is compared by PACT's own typed
  comparator against a `double`, so the CEL `dyn()` problem cannot arise.

**Composition beyond AND.** Structural, not textual, and **structurally exclusive** with
atoms (Portkey bug 1):
```yaml
requires:
  all_of: [ … ]        # default when `requires:` is a bare list
  any_of: [ … ]
  none_of: [ … ]
```
A node containing `all_of`/`any_of`/`none_of` **may contain no other key**. Validation
error otherwise, with a two-span diagnostic.

**Tier 1 (expert escape, never required — D14 remains satisfied because Tier 0 is
complete):** a `cel:` field accepting a **restricted CEL profile**:
- Macros **disabled** (sanctioned at `langdef.md:901`).
- Arithmetic, string concatenation and list/map construction **disabled**.
- Allowed: `== != < <= > >= in`, `&& || !`, `?:`, `has()`, `size()`, field selection,
  literals — a superset of both empirical minimum sets in §1.4.
- All catalogue numerics declared `double`; integer literals promoted at compile time
  (necessary per `comparisons.textproto:21-66`).
- **`&&`/`||` lowered to `?:` before evaluation** so PACT gets left-to-right short-circuit
  and does *not* inherit CEL's error-swallowing commutativity (`langdef.md:661-672` gives
  the exact rewrite).
- **Three-valued lifting**: a reference to an absent catalogue figure yields `unknown`,
  which propagates (`unknown && false = false`, `unknown && true = unknown`), rather than
  CEL's `false`.
- **Every Tier-1 expression must round-trip to Tier 0 when it is expressible there**, and
  the UI must render it as structured atoms. Otherwise Tier 1 becomes the de-facto surface
  and D14 is lost.

**Every predicate — Tier 0 or Tier 1 — carries a mandatory `because:` string**, exactly
Crossplane's `message=` (50/50 rules) and CEL-policy's `explanation`
(`policy.proto:57`) and KCL's check message (§2.3).

**Air-gap note (D17).** CEL's canonical AST serialization is protobuf
(`config/cel-spec/README.md:44-50`); reference implementations are Go/Java/C++; there is no
Rust CEL in the corpus. Tier 0 needs neither — it is a Rust `match`. **This is a further
reason to make Tier 0 total and Tier 1 optional.** If Tier 1 ships, the 2,855-case
conformance suite gates it offline.

---

## 2. Schema and validation: error messages a non-coder can act on

### 2.1 JSON Schema deliberately does not solve this

The output specification defines **structure only** — `evaluationPath`, `schemaLocation`,
`instanceLocation`, `valid`, `errors`, `details`
(`protocols/json-schema-spec/specs/output/jsonschema-validation-output-machines.md:37-53,84-96`)
— and then explicitly disclaims wording:

> "Note that the error message wording as depicted in the examples below is **not a
> requirement of this specification**. Implementations SHOULD craft error messages tailored
> for their audience **or provide a templating mechanism that allows their users to craft
> their own messages**."
> — `jsonschema-validation-output-machines.md:181-184`

The core spec repeats the deferral: "this specification defers the details of any output
formats to other documents" (`specs/jsonschema-core.md:2036-2040` region; the section
header is at `## Output Formatting {#output}`).

**⇒ PACT must own the message layer.** JSON Schema is a good *shape* checker and a good
*location* reporter; it is not, and does not claim to be, a UX.

### 2.2 What that actually costs, measured

I took a **valid** 24-line example from the Serverless Workflow spec's own CI-gated
example set (`protocols/serverless-workflow/examples/call-http-query-parameters.yaml`),
validated it against the spec's own 1,974-line JSON Schema 2020-12 document
(`schema/workflow.yaml`) with a conformant validator, confirmed it passes, then introduced
three realistic non-coder mistakes. [executed — Appendix A.2]

| Mutation | Top-level errors | **Total output units incl. nested `context`** |
|---|---:|---:|
| `call:` mistyped as `cal:` | 2 | **65** |
| stray key `than: end` (meant `then:`) | 2 | **64** |
| `version: '1.0.0'` → `'1.0'` (fails the semver `pattern`) | 2 | **2** |

The 65-unit report for a one-character typo contains, verbatim:

```
Unevaluated properties are not allowed ('cal', 'with' were unexpected)
'do' is a required property
'fork' is a required property
'emit' is a required property
'for' is a required property
'listen' is a required property
'raise' is a required property
'run' is a required property
'set' is a required property
'switch' is a required property
'try' is a required property
'catch' is a required property
'wait' is a required property
```

The author mistyped `call`. The validator's advice is to add **eleven mutually exclusive
keys they never wanted**, and the word `call` never appears. This is the `oneOf` error
explosion in its natural habitat: the task node is a 12-branch union
(`dsl.md:168-181`), so one typo fails all twelve branches and every branch reports.

> **⇒ PACT rule (discriminate before validating).** Every polymorphic node carries an
> explicit discriminator (`kind:`), the loader selects exactly one schema, and validation
> errors are reported against *that schema only*. This is why Serverless Workflow, OAM and
> Crossplane are all discriminator-first in their data model
> (`protocols/oam-spec/6.traits.md:40-42`; `serverless-workflow/dsl.md:168-181`) — they
> just do not exploit it in their *error reporting*.

### 2.3 The `unevaluatedProperties` false diagnosis — a spec-level trap, not a bug

The third mutation above is the more dangerous result. Changing `version: '1.0.0'` to
`'1.0'` — a *value* error on a *declared* field — produces:

```
path=['document']            | Unevaluated properties are not allowed ('version' was unexpected)
path=['document','version']  | '1.0' does not match '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|…
```

**The first message is false.** `version` *is* a declared property of `document`. The
author is told the field does not exist when in fact its value is wrong. And this is
required by the specification, not a validator defect. The causal chain, all three links
normative:

1. `document.version` fails its `pattern`, so the `properties` subschema for `version`
   fails.
2. > "The only exception is that subschemas of a schema object that has failed validation
   > MAY be skipped, as **annotations are not retained for failing schemas**."
   > — `specs/jsonschema-core.md:706-708`

   ⇒ `properties` produces no annotation marking `version` as evaluated.
3. > "This keyword applies its subschema to any property values which **have not been
   > deemed 'evaluated'**."
   > — `specs/jsonschema-core.md:1937-1939`; and the behaviour "depends on **all adjacent
   > keywords as well as keywords in successfully validated subschemas**" (`:1931-1935`).

   ⇒ `unevaluatedProperties: false` sees `version` as unevaluated and reports it as
   unexpected.

The spec knows this is a debugging problem and offers "dropped annotations" as the fix —
then rules them out as a default:

> "A dropped annotation is any annotation produced and subsequently dropped by the
> evaluation due to an unsuccessful validation result of the containing subschema. …
> implementations that wish to provide dropped annotations **SHOULD NOT provide them as
> their default behavior**."
> — `specs/jsonschema-core.md:2022-2031`

> **⇒ PACT rule (blocking).** Never use `additionalProperties: false` or
> `unevaluatedProperties: false` as the unknown-key mechanism. Unknown-key detection is a
> **separate pass** over the closed key set for the discriminated `kind`, run *after* and
> *independently of* shape validation, so a wrong value can never masquerade as an unknown
> field. This also sidesteps the older trap that `additionalProperties` "depends on the
> presence of `properties` and `patternProperties` **within the same schema object**"
> (`jsonschema-core.md:1780-1783`), which makes the natural idiom
> `allOf: [{$ref: '#/agentBase'}, {additionalProperties: false}]` reject every inherited
> field.

Two further JSON Schema traps that hit PACT specifically:

- **Raw regexes reach the author.** The semver `pattern` above is 130 characters of PCRE
  printed verbatim. PACT must map every `pattern` to a human phrase in its rule catalogue
  (`expected: a version like 1.4.0`), and never print the regex outside `--debug`.
- **`format:` is not portable.** "Implementations **SHOULD** provide assertion behavior for
  the format values defined by this document **and MUST refuse to process any schema which
  contains a format value it doesn't support**"
  (`specs/jsonschema-validation.md:345-347`), and custom formats "**MUST be configurable
  and disabled by default**" (`:367`). With adapters out-of-tree in Rust, Python and
  TypeScript (D4), the *same document* would validate differently per validator, and a
  custom `format: pact-duration` would make the schema **unprocessable** by a conformant
  validator. ⇒ PACT expresses durations/sizes as **suffixed strings with a PACT-owned
  parser** (`30s`, `128k`), never `format:`.

### 2.4 The good exhibits, ranked

**(a) KCL — the best *diagnostic layout* in the corpus.** Real golden output, not
documentation (`config/kcl/tests/grammar/schema/type/type_fail_0/stderr.golden`):

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

Six things to copy:
1. **Stable machine code** `E2G22`, resolvable to an in-repo Markdown page —
   `config/kcl/crates/error/src/error_codes/E2G22.md`; **12 error-code pages** ship in the
   repo, so the docs work air-gapped.
2. Primary span with a caret at the *offending value*.
3. **Expected vs got, with the actual value inlined** — `got str(Doe)`, not `got str`.
4. **A second span pointing at the declaration that was violated** — "variable is defined
   here". This answers *"says who?"*, and it is the single most under-used technique in the
   corpus.
5. Docs pages carry a **"Possible resolution:"** section (`E2D34.md`, `E1001.md`).
6. **Did-you-mean from the closed key set**:
   `Cannot add member 'frist' to schema 'Person', did you mean '["first"]'?`
   (`tests/grammar/schema/mixin/add_member_fail/stderr.golden`). Implementation:
   `crates/sema/src/resolver/attr.rs:128-160` collects `schema_ty.attrs.keys()` then calls
   `suggestions::provide_suggestions` (crate `suggestions = "0.1.1"`,
   `crates/sema/Cargo.toml:34`). Same technique at `resolver/scope.rs:430-446`,
   `resolver/config.rs:460,488`, `resolver/arg.rs:171`.

**(b) KCL — author-written check messages. [NEW]** This is the closest shipping analogue
of PACT's mandatory `because:`, and the corpus contains both the good and the bad case in
adjacent test directories.

*With* a message (`tests/grammar/schema/check_block/check_block_fail_5/main.k:5-7`):
```
    check:
        name, "name should be defined and not empty"
        labels, "labels should be defined and not empty"
```
renders as (`.../check_block_fail_5/stderr.golden`):
```
error[E3M38]: EvaluationError
 --> ${CWD}/main.k:9:11
  |
9 | JohnDoe = Person {
  |           ^ Instance check failed
  |
 --> ${CWD}/main.k:6:1
  |
6 |         name, "name should be defined and not empty"
  |  Check failed on the condition: name should be defined and not empty
  |
```
Two spans — the *instance* the author wrote and the *rule* that rejected it — plus the
author's own sentence. That is the target shape.

*Without* a message (`check_block_fail_2/main.k:10-11` → `.../stderr.golden`):
```
 --> ${CWD}/main.k:11:1
  |
11 |         12 <= age <= 18
  |  Check failed on the condition
  |
```
The rule is echoed as source text, and **the actual value (`age = 19`) is never printed**.
An author who did not write the rule cannot act on this.

> **⇒ PACT rule:** `because:` is **mandatory**, not optional, on every author-written rule
> (predicate, eval gate, SLO gate, policy). The validator rejects a rule without one. An
> unexplained rule is an unactionable failure, and KCL ships the proof in a golden file.

**(c) KCL's cascade defect — the counterweight to "report all errors".** One malformed
line produces **four** errors, three of them at the identical position
(`check_block_fail_0/main.k:12` → `stderr.golden`, four `error[E1001]` blocks at 12:19,
12:27, 12:27, 12:27):
```
12 |         (lastName not None)
   |                   ^ expected one of [")"] got identifier
   |                           ^ expected one of ["identifier", "literal", "(", "[", "{"] got )
   |                           ^ expected expression, got )
   |                           ^ expected one of ["identifier", "literal", "(", "[", "{"] got newline
```
⇒ "report all errors" must be qualified: **report all *independent* errors, and collapse
cascades.** PACT's loader must (i) stop parser recovery from emitting more than one
diagnostic per source position, and (ii) suppress downstream semantic errors whose input
node is already `Error`.

**(d) KCL's two shipped message bugs**, which are the cautionary half:
- `can't change schema field type of 'firstName' from int to int`
  (`tests/grammar/schema/inherit/inherit_change_field_type_0/stderr.golden:6`) — nonsense,
  shipped in a golden file. **Format is not content**; every message string needs its own
  review.
- The suggestion is Rust-`Debug`-formatted: `'["first"]'` rather than `'first'`. Message
  *rendering* needs the same care as message *authoring*.

**(e) Pkl — the best *failure explanation* in the corpus.**
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

xx | max = 3
           ^
at constraints5#res2.max (…)
```

A **sub-expression value trace**: every operand's runtime value printed under the operator
that consumed it, plus the operator's own result. For `MMLU > 80 && SWE-Verified > 40` this
is exactly the output PACT needs when the resolver refuses to bind a model — and it is
exactly what CEL cannot give you (`explain.proto:28`, deprecated).

Pkl also externalises its whole message catalogue: **1,210 lines** in
`pkl-core/src/main/resources/org/pkl/core/errorMessages.properties`, with *graded* variants
per situation (`:367-406`): `cannotFindPropertyInScope`,
`cannotFindPropertyInScopeListCandidates` (+ "Did you mean any of the following?"),
`cannotFindPropertyInModule`, `cannotFindPropertyInModuleListCandidates`,
`cannotFindPropertyInObject`, `cannotFindPropertyInObjectListCandidates`,
`cannotFindPropertyInObjectNoHint` (explicitly hint-free), `cannotFindPropertyInType`,
`cannotFindPropertyInType2`. Nine variants of one error, chosen by how much context is
available. That is what a mature message catalogue looks like.

**The Pkl anti-pattern to avoid:** the same `.err` file ends with two frames of
implementation internals:
```
xxx | renderer.renderDocument(value)
at pkl.base#Module.output.text (pkl:base)
xxx | if (renderer is BytesRenderer) renderer.renderDocument(value) else …
at pkl.base#Module.output.bytes (pkl:base)
```
Two of the four frames are the author's; two are Pkl's own stdlib. A support lead reading
this concludes the tool is broken. **PACT must have an explicit "user frames only" filter
on stack rendering.**

**(f) OPA's `failtracer` — the answer to "why did nothing match". [NEW]** OPA ships a
tracer that produces did-you-mean hints for **undefined data references at evaluation
time** (`config/opa/v1/server/failtracer/failtracer.go`):

```go
const maxDistanceForHint = 3      // :15  levenshtein distance below which we emit a hint
...
case 1:  msg = fmt.Sprintf("%v undefined, did you mean %s?", ref, proposals[0])            // :114
default: msg = fmt.Sprintf("%v undefined, did you mean any of %v?", ref, proposals)        // :116
```
Real outputs, from its tests (`failtracer/hints_test.go:38,64,83-84`):
```
input.fruit.price undefined, did you mean input.fruits.price?
input.prize undefined, did you mean input.price?
```
The algorithm is fully transferable and worth copying line-for-line:
- hooks the evaluator's **`FailOp`** events (`:43-49`) — i.e. it explains why something was
  *undefined*, the hardest class of error in a declarative system;
- Levenshtein threshold **3** (`:15`);
- deduplicates by reference (`seenRefs`, `:93-96`);
- **suppresses no-op suggestions** — if the miss is already a declared unknown, it stays
  silent rather than suggesting the thing you typed (`:86-92`);
- distinct message forms for one candidate vs several (`:111-116`).

> **⇒ PACT rule:** the resolver's `PORTABILITY: FAIL` path (D11) is a `failtracer`. When a
> capability, benchmark, tool, skill or agent name does not resolve, emit
> `benchmark "MMLU-Pro" is not in the catalogue for qwen3-4b — did you mean "MMLU"?`
> with the same three rules: distance cap, dedup, and no-op suppression.

### 2.5 The failure modes to design against — CUE as the negative control

CUE is the most powerful validator in the corpus and produces the least actionable
messages:

| Real CUE output | File:line | Why a non-coder is stuck |
|---|---|---|
| `bar: 2 errors in empty disjunction:` | `config/cue/cmd/cue/cmd/testdata/script/eval_errs.txtar:7` | "disjunction" is not in the user's vocabulary; the count is a red herring |
| `conflicting values "str" and int (mismatched types string and int)` | `eval_errs.txtar:8` | Says *what* conflicts, never *which one you should change* |
| `translations.hello.lang: incomplete value string:` | `.../vet_file.txtar:8` | "incomplete value" means "you didn't fill this in", but does not say so |
| `field not allowed:` | `config/cue/cue/testdata/fulleval/035_optionals_with_label_filters.txtar:35` | **No did-you-mean anywhere in the CUE evaluator.** Grep finds `did you mean` only in cobra CLI arg handling (`cmd/cue/cmd/testdata/script/unknown_args.txtar:53`) |
| `2 errors in empty disjunction::` (double colon) | `config/cue/cue/testdata/builtins/error.txtar:113` | Cosmetic, but shipped |

CUE *does* have `error("custom message")` and it works
(`config/cue/cue/testdata/builtins/error.txtar:8,30,81`). Two problems:
1. The idiom is `x: int | error("I wanted an integer")` — a disjunction with bottom.
   Expert-only syntax.
2. **Aggregation is inconsistent, admitted by CUE's own maintainers.** Three
   constraint/message pairs on one field produce `2 errors in empty disjunction`, reporting
   only two of three, with the maintainer note *"we could also include the third condition,
   if we want to be consistent."* (`error.txtar:81-90`). A user `error()` inside a pattern
   constraint is *lost* and the generic `field not allowed` shown instead — filed as
   cuelang.org/issue/4208, encoded as `@test(err:todo, …)` at
   `config/cue/cue/testdata/builtins/issue4208.txtar:1-2,15`.

**And the biggest single usability defect in the corpus, re-verified:**

> `// AllErrors causes all errors to be reported (not just the first 10 on different lines).`
> — `config/cue/cue/parser/interface.go:131`
> CLI default is **off**: `f.BoolP(string(flagAllErrors), "E", false, "print all available errors")`
> — `config/cue/cmd/cue/cmd/flags.go:104`, consumed at `cmd/cue/cmd/common.go:668`

A non-coder fixing a 3-agent workspace gets one error, fixes it, gets another, fixes it…
**PACT must report every independent error in one pass, by default, with no flag** — with
the cascade-collapsing qualification from §2.4(c).

### 2.6 Recommended validation strategy for PACT

**Pipeline (all offline, D17):**

```
tree ──► CST parse (positions + comments kept) ──► collapse parser cascades ──►
   discriminate by `kind:` ──►
   shape check (JSON Schema, per-kind, NO additionalProperties/unevaluatedProperties) ──►
   key check (closed key set for that kind + did-you-mean) ──►
   reference check (every name/`$ref` resolves; failtracer hints on misses) ──►
   rule check (PACT rule catalogue; structured predicates, three-valued) ──►
   report ALL independent findings, sorted by file/line
```

**The PACT diagnostic record** (normative shape — every emitter fills all fields):

```yaml
code: PACT-E0142                    # stable, documented, greppable        (KCL E2G22)
severity: error | warning
title: "Unknown field 'temprature' on agent"
where:                              # PRIMARY span — the thing the author typed
  file: agents/researcher/agent.yaml
  line: 12
  col: 3
  excerpt: "  temprature: 0.7"
because:                            # SECONDARY span — the rule that rejected it (KCL)
  file: <builtin>/schema/agent.yaml
  line: 88
  note: "the Agent kind declares 14 fields; 'temprature' is not one of them"
actual: 0.7                         # value inlined                        (KCL got str(Doe))
expected: "one of: temperature, top_p, top_k, …"
suggestion:
  did_you_mean: temperature         # levenshtein ≤ 3, no-op suppressed    (OPA failtracer)
  fix: "rename 'temprature' to 'temperature'"
docs: pact://errors/E0142           # in-repo Markdown page, air-gapped    (KCL error_codes/)
```

Rules, each with its evidence:
- **Stable code + in-repo docs page.** KCL ships 12 as Markdown under
  `crates/error/src/error_codes/`; PACT ships its own under `docs/errors/` so they work
  air-gapped (D17).
- **Two spans always.** Primary = author's text; secondary = the declaration violated.
  From `kcl/tests/grammar/schema/type/type_fail_0/stderr.golden` and
  `check_block/check_block_fail_5/stderr.golden`.
- **Did-you-mean is mandatory for any closed key set**, computed from the schema, rendered
  as a bare identifier not a debug-formatted list (KCL's `'["first"]'` bug).
- **Value inlined**, KCL's `got str(Doe)` rather than `got str`; and for check failures the
  *observed* value, which KCL omits (§2.4(b), the negative case).
- **Sub-expression trace on every failed predicate**, Pkl style (`constraints5.err`). For
  structured predicates this is free: report the atom, its observed value, its threshold,
  and whether the value was `absent`.
- **User frames only.** Never print PACT-internal evaluation frames (Pkl's `pkl:base` leak).
- **All independent errors, every run.** No `-E` (`cue/cmd/cue/cmd/flags.go:104`), and no
  cascades (KCL `check_block_fail_0`).
- **`because:` is authorable and required.** Crossplane 50/50 `message=`, CEL-policy's
  per-match `explanation` (`policy.proto:57`), KCL's check message.
- **Never `oneOf` to the author** — discriminate first (§2.2, the 65-unit measurement).
- **Never `additionalProperties`/`unevaluatedProperties` for key checking** (§2.3, the
  false diagnosis).

**Two-tier authorship, made explicit.** KubeVela and Crossplane both split roles and say
so: "the distinction is only important to the people *authoring* the Compositions, never to
the people *consuming* them"
(`config/crossplane/design/design-doc-composition-functions.md:128-131`). D14 forbids that
split for *capability*, but not for *responsibility*: the non-coder must be able to express
everything, but **the schema and message catalogue are PACT-authored**. Every message a
domain expert sees comes from a catalogue PACT wrote and tested.

---

## 3. Defaulting, inheritance and overlay semantics

### 3.1 Defaults must not live in the schema — a JSON Schema finding [NEW]

> ### `default`
> "There are no restrictions placed on the value of this keyword. When multiple occurrences
> of this keyword are applicable to a single sub-instance, implementations SHOULD remove
> duplicates. … It is **RECOMMENDED** that a default value be valid against the associated
> schema."
> — `protocols/json-schema-spec/specs/jsonschema-validation.md:694-702`

Three consequences, all fatal for a no-code system that puts defaults in its schema:

1. **A `default` need not be valid against its own schema.** Only RECOMMENDED. So the
   schema can ship a default that the validator would reject.
2. **Validators do not inject defaults.** `default` is under "Keywords for Basic Meta-Data
   Annotations" (`:678`) — it is an annotation, full stop. Anything that materialises
   defaults is out-of-spec behaviour that differs per implementation, and PACT's adapters
   are out-of-tree in three languages (D4).
3. **Multiple applicable defaults have no resolution rule** — the spec says only "SHOULD
   remove duplicates", which handles identical values and says nothing about *different*
   ones. This is exactly CUE's `(*1|2) & (1|*2) ⇒ bottom` problem
   (`config/cue/doc/ref/spec.md:820`), except CUE at least *errors*; JSON Schema is silent.

> **⇒ PACT rule (blocking).** Defaults live in **profiles**, not in the JSON Schema. The
> schema may carry `default:` **for documentation and form pre-fill only**, and a CI test
> asserts (a) every schema `default` validates against its own subschema, and (b) every
> schema `default` is byte-equal to the built-in profile value for that path. This is
> also what makes F-1 ("no hardcoded defaults that cap capability") and AC-7.2
> mechanically checkable: there is exactly one place to audit.

### 3.2 The four config-language models, and how each fails

| Model | Mechanism | Nested maps | Lists | Failure mode |
|---|---|---|---|---|
| **Jsonnet** | `+` operator + 6 field separators | **replace** | replace (concat with `+:`) | `:` `::` `:::` `+:` `+::` `+:::` — merge behaviour *and* visibility encoded in punctuation |
| **CUE** | unification (`&`) + marked disjunction defaults | merge (unify) | element-wise unify | two different defaults for one field ⇒ **bottom** |
| **Pkl** | `amends` chain + late binding | merge (amend) | **index-addressed** amend | positional list overrides; non-local effects via late binding |
| **OAM/KubeVela** | typed traits, ordered, `conflictsWith` | n/a (one instance per kind) | n/a | no `requires`; trait-name/workload-param namespace collision |

**Jsonnet** — "By default nested objects are **completely replaced** when overriden"
(`config/jsonnet/doc/ref/language.html.md:479`). Opt-in deep merge with `+:`, which also
concatenates arrays (`:541`). "The number of colons determines the **visibility** of the
field" (`:541`) — so one punctuation mark encodes two orthogonal decisions. And
`{ foo +: {…} }` with no left-hand match is silently fine (`:543`). It desugars to
`{ a: if "a" in super then super.a + b else b }` (`:545`) — the author is writing
conditional inheritance in punctuation. Jsonnet's own roadmap lists "More object
orientation: mixins, **diamond problem**, definition of `+:` (!)" as open work (`:697`).

**CUE** — defaults are marked disjuncts (`config/cue/doc/ref/spec.md:756-762`), governed by
rewrite rules U0–U2, D0–D2, M0–M3 (`:783-804`). The killer:
```
(*1|2) & (1|*2)   ⇒   ⟨1|2, _|_⟩        — spec.md:820
```
Two layers each asserting a *different* default for the same field unify to **bottom**. In
a PACT workspace: workspace profile says `temperature` defaults to 0.2, the `small` variant
says 0.7 ⇒ hard error reading `2 errors in empty disjunction`. **Unification-based
defaulting is disqualified for a no-code system.**

**Pkl** — `amends` is clean for maps, and the typed/dynamic split is exactly the
closed/open-schema distinction PACT needs:

> "When a **dynamic** object is amended, not only can existing properties be overridden or
> amended, but new properties can also be added. When a **typed** object is amended, its
> properties can be overridden or amended, **but new properties cannot be added**."
> — `config/pkl/docs/modules/language-reference/pages/index.adoc:832-835`

But two hazards:
1. **Lists are amended by index** (`index.adoc:1390-1412`):
   ```
   birds2 = (birds) {
     new { name = "Barn owl" }   // appends
     [0] { diet = "Worms" }      // amends element 0
     [1] = new { … }             // replaces element 1
   }
   ```
   Insert one element at the top of the base and every override silently retargets.
2. **Late binding makes overrides non-local.** Pkl's own framing: "object properties behave
   like **spreadsheet cells** … changes to 'downstream' properties automatically propagate"
   (`index.adoc:770-776`). Worked example: overriding `eggIncubation` from `40.d` to `11.d`
   silently changes `adultWeightInGrams` from 4000 to 1100 (`index.adoc:741-767`). For
   listings likewise: overriding element 0's `diet` changes element 1's, because element 1
   was defined as `(this[0]) { … }` (`index.adoc:1436-1449`). **What you read in the file
   is not what runs.** For a non-coder reviewing a git diff (D18 surface 4) this is fatal:
   the diff shows one changed line and the behaviour change is elsewhere.

**OAM traits** — the most predictable model in the corpus, and the one to copy:
- "**A component instance may only have one configuration of any given trait type.**"
  (`protocols/oam-spec/6.traits.md:67`) ⇒ no ambiguity about which `autoscaler` wins.
- "Apply the traits in the **defined order**" and "Determine compatibility, and **fail** if
  the combination of traits cannot be satisfied" (`6.traits.md:60-65`).
- `conflictsWith: []string` declared **on the trait definition**, not discovered at merge
  time (`6.traits.md:31`).
- Ordering preserved by representation choice, stated in the Go type: `// Traits define the
  trait of one component, **the type must be array to keep the order**`
  (`config/kubevela/apis/core.oam.dev/common/types.go:363`).
- **Negative:** "There is **no mechanism for explicitly requiring a combination of traits**"
  (`6.traits.md:73`). PACT needs `requires:` as well as `conflicts_with:` (a `computer_use`
  tool requires a `sandbox` policy, D16).
- **Namespace hazard:** in KubeVela's Appfile, "there is a restriction that the trait type
  should not conflict any of the Workload parameters' first level name"
  (`config/kubevela/design/vela-core/appfile-design.md:192`) — traits and workload params
  share a flat namespace, so adding a trait can shadow a field. PACT must keep resource
  kinds in their own namespace (`tools:`, `skills:`, `policies:`), never flat.

### 3.3 Helm, measured [NEW]

The corpus contains no standalone Helm repo, but it contains three real charts. The LiteLLM
chart (`routing/litellm/helm/litellm-helm/`) is the fullest and is worth quantifying,
because it is what "config with a templating escape hatch" costs after a few years.

[executed — Appendix A.4]

| Measure | Value |
|---|---:|
| Template lines (`templates/*.yaml` + `_helpers.tpl`) | **839** |
| Lines containing `{{` | **513 (61%)** |
| `values.yaml` lines | 456 |
| **Lines of unit tests** (`tests/*.yaml`, helm-unittest) | **1,434** |
| **Test-to-template ratio** | **1.71 : 1** |
| Distinct `nindent` call sites | **66** |

Per-file density: `configmap-litellm.yaml` 77%, `ingress.yaml` 75%, `keda.yaml` 67%,
`migrations-job.yaml` 62%, `_helpers.tpl` 62%, `deployment.yaml` 59%,
`extra-resources.yaml` 100%.

**These files are not YAML.** They are Go `text/template` programs that emit YAML, and the
failure modes are visible in fifty lines:

1. **Indentation is hand-computed arithmetic.** `{{- toYaml .Values.podSecurityContext |
   nindent 8 }}` (`templates/deployment.yaml:47`), `nindent 12` at `:55`, `nindent 4` at
   `:5`, `nindent 6` at `:22`. 66 call sites. Change the nesting depth of a block and every
   `nindent` integer inside it must change. There is no checker for this; the failure is a
   malformed document at install time.
2. **A second template evaluation over user-supplied values.** `{{- tpl (toYaml .) $ |
   nindent 8 }}` (`deployment.yaml:33` for `podAnnotations`, `:50` for
   `extraInitContainers`). Values written by the *user* are executed as templates. That is
   the injection surface Serverless Workflow explicitly forbids (`dsl.md:387`), reinvented.
3. **Cross-file non-local dependency.** `checksum/config: {{ include (print
   $.Template.BasePath "/configmap-litellm.yaml") . | sha256sum }}` (`deployment.yaml:30`)
   — one template renders another template to hash it.
4. **The only error mechanism is a string on a value fetch.** `{{ required
   "billingMetrics.endpoint is required when billingMetrics.enabled is true"
   .Values.billingMetrics.endpoint | quote }}` (`_helpers.tpl:63`). The message is good —
   as good as Crossplane's — but it fires at *render* time, with no file:line into the
   `values.yaml` the user actually wrote. **Good message, wrong location, wrong time.**
5. **Conditionals as whitespace-sensitive comments.** `{{- if and (not
   .Values.keda.enabled) (not .Values.autoscaling.enabled) }}` (`deployment.yaml:13`) —
   boolean logic in a language whose only type discipline is whether you remembered the
   dash.

> **⇒ The finding is the ratio.** When configuration becomes a template program, it
> acquires a *test suite* — 1,434 lines of it, more than the templates themselves. A
> non-technical domain expert (D13) cannot write helm-unittest assertions, so under a
> templating model they are structurally locked out of verifying their own config. This is
> the concrete form of D28 failure mode #1.

### 3.4 Kustomize, read [NEW]

`eval/phoenix/kustomize/` is a complete two-layer overlay: a base
(`base/kustomization.yaml` — 3 lines) and an `auth` overlay (`auth/kustomization.yaml` — 5
lines, `auth/patches.yaml` — 22 lines).

The overlay's entire *purpose* is to add two environment variables. To do that,
`auth/patches.yaml` restates the full path to them:

```yaml
apiVersion: apps/v1        # 1
kind: StatefulSet          # 2
metadata:                  # 3
  name: phoenix            # 4
spec:                      # 5
  template:                # 6
    spec:                  # 7
      containers:          # 8
      - name: phoenix      # 9
        env:               # 10
        - name: PHOENIX_ENABLE_AUTH     # ← payload
          value: "true"
        …
```
**Nine lines of coordinate scaffolding for four lines of payload.**

**The failure mode, stated precisely:** *nothing in either file says whether the base's
three environment variables survive.* The base declares `PHOENIX_WORKING_DIR`,
`PHOENIX_PORT` and `PHOENIX_SQL_DATABASE_URL` (`base/phoenix.yaml:27-32`). The overlay
declares two more. Whether the result has 2 or 5 depends on a merge key (`name`) that
appears in **neither file** — it is a property of the upstream Kubernetes type definition,
and the overlay author must know it from outside the tree. The evidence that this is
recognised as a hazard is that Kubernetes CRDs document merge behaviour *per field, in
prose, inside the schema*: "This array is **replaced** during a strategic merge patch"
(`config/kubevela/pkg/workflow/providers/legacy/query/testdata/gateway/crds/gateway.networking.k8s.io_gateways.yaml:245`).
**A merge semantics that must be documented per field is a merge semantics the author
cannot predict.**

Two further observations from the same 22 lines:
- The file uses the legacy `bases:` and `patchesStrategicMerge:` spellings
  (`auth/kustomization.yaml:1,4`) — overlay tooling drifts, and overlay files are exactly
  the files nobody revisits.
- A literal secret is checked in at `auth/patches.yaml:22`, immediately below a comment
  (`:13-20`) explaining that you must instead use `valueFrom.secretKeyRef`. Overlay files
  accumulate examples-as-values, because the overlay is the place where "just make it work"
  edits land.

### 3.5 The Dhall antidote

> "Every Dhall configuration file can be reduced to a **normal form** which eliminates all
> abstraction and indirection."
> — `config/dhall-lang/README.md:145-147`

offered explicitly as the answer to the objection "Configuration languages become
unreadable due to abstraction and indirection" (`:143-147`). Dhall also guarantees
"Evaluation always terminates, no exceptions or crashes. Ever." (`:129-143`) and
deliberately impoverishes itself — "you cannot even compare strings for equality"
(`:150-152`).

### 3.6 Recommendation — PACT overlay semantics

**S1. One linear resolution chain, no diamonds.**
`built-in defaults → profile → workspace → agent → variant → run override`. Six named,
ordered layers; **later wins**. No multiple inheritance, no mixins, no diamond. This is
Pkl's amend chain minus the graph, and OAM's ordered trait list. Every non-determinism
complaint in the corpus (CUE bottom-on-conflicting-defaults, Jsonnet `super` chains and its
own "diamond problem" TODO at `language.html.md:697`, Kustomize's undeclared merge keys)
originates in a merge *lattice* rather than a merge *list*.

**S2. Scalars and maps: replace-by-default; deep merge is opt-in and explicit.**
Follow Jsonnet's default (`language.html.md:479`), reject CUE's unify-by-default. Opt-in
spelled as a field-level directive the author can see:
```yaml
tools:
  merge: append          # replace (default) | append | by_key
```
Never punctuation. Jsonnet's six separators are the counter-example.

**S3. Lists: identity is a `name:` key, never an index.** Every overridable list element
**must** carry a unique `name:`; overlays address elements by name; unnamed elements are
append-only and non-overridable. Counters Pkl's `[0] { … }` (`index.adoc:1398-1404`) and
Kustomize's invisible merge key (§3.4).

**S3a. Merge semantics are declared *in the schema*, per field, and printed in the
diagnostic.** The Kustomize failure is not that strategic merge is wrong; it is that the
rule lives outside the tree. PACT's schema carries `x-pact-merge: replace|append|by_key`
on every collection field, `pact explain --field <path>` prints it, and the form UI shows it
next to the field.

**S4. At most one instance of a kind per parent.** `oam-spec/6.traits.md:67` in spirit.
Two `memory:` blocks on one agent is a validation error, not a merge.

**S5. Declared conflicts and declared requirements.** `conflicts_with:` (OAM has it,
`6.traits.md:31`) **and** `requires:` (OAM lacks it and says so, `6.traits.md:73`). Both
declared on the *definition*, checked at load, reported with the two-span diagnostic.

**S6. No late binding across layers. No lazy cross-references in authored config.** A value
is either a literal or an explicit `${ref:…}` to a *named* resource — never an expression
over sibling fields whose value changes when a sibling is overridden. This forfeits Pkl's
"secret sauce" (`index.adoc:737-780`) on purpose: the cost of the spreadsheet model is that
a git diff stops being a behaviour diff, and D18 surface 4 makes git diff first-class.

**S7. `pact explain` is a required CLI verb, not a nicety.** Three modes:
- `pact explain agents/researcher` → fully resolved document, all abstraction removed
  (Dhall normal form, `dhall-lang/README.md:145-147`);
- `pact explain agents/researcher --field temperature` → the value, **the layer it came
  from** with file:line, and the merge rule that applied, for every layer that touched it;
- `pact explain --diff` → resolved-form diff between two revisions, so a reviewer sees the
  *behavioural* delta.

**S8. Defaults live in profiles and are printed.** `pact explain --defaults` lists every
default, its value, and the profile that set it. Schema `default:` is documentation only
and is CI-checked against the profile (§3.1).

---

## 4. Control flow without becoming a bad programming language

### 4.1 The Crossplane post-mortem — still the single most important document in this corpus

`config/crossplane/design/design-doc-composition-functions.md` is a first-party account of
an organisation that (a) deliberately refused to build a DSL, (b) built one by accident
anyway, and (c) killed it.

**The intent** (`:94-120`):
> "Avoid organically growing a new configuration Domain Specific Language (DSL). These
> languages tend to devolve to incoherency as stakeholders push to 'bolt on' new
> functionality to solve pressing problems at the expense of measured design. **Terraform's
> DSL supporting the `count` argument in some places but not others** is a great example of
> this."
>
> "It was also important to avoid the 'worst of both worlds' … To this end **we omitted
> common language features such as conditionals and iteration.**"

**What happened** (`:132-149`):
> "Many Compositions call for a high level of expressiveness — conditionals, iteration,
> merging data from multiple fields, etc."
> "**The lack of a more expressive alternative to P&T Composition _has_ set us down the path
> of organically growing a new DSL.**" — followed by **twelve** issue numbers (#1972, #2352,
> #4051, #3917, #3919, #3989, #3498, #3458, #3316, #4036, #4065, #4026).
> "Organically growing a new DSL is not only undesirable, but **slow**. Because each
> addition to P&T Composition changes Crossplane's core API … Changes take a long time to
> reach consensus. They're coupled to Crossplane's release cycle."

**The resolution** (`:186-196`): `mode: Pipeline` — an ordered array of out-of-tree,
OCI-packaged functions, each feeding the next. **And it stuck.** In current source,
patch-and-transform is gone from the API:
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
(`config/crossplane/design/one-pager-function-go-templating.md:38-70`). **The escape hatch
became Helm** — and §3.3 measures what that costs.

**Consequences for PACT, stated plainly.** D14 forbids "experts write code for this".
Crossplane's history says that refusing expressiveness does not prevent a DSL — it
guarantees a *worse* one, accreted under issue pressure, coupled to the core release cycle.
Therefore PACT must:
- Choose its control-flow vocabulary **closed and sufficient on day one**, from evidence,
  not by accretion (§4.4).
- Put the extension point **outside the core release cycle** (out-of-tree, versioned) —
  already planned for adapters (E-1) and optimizers (E-5); extend it to loop/topology node
  kinds (G-2, G-3).
- **Never** make the extension point "a string of another language". That is the KubeVela
  `template: |` pattern (§5.3) and the Crossplane go-templating pattern, and it is how you
  get Helm.

### 4.2 The Serverless Workflow autopsy — now executable

**What works, and PACT should copy:**

1. **A closed 12-verb task vocabulary**: `Call, Do, Emit, For, Fork, Listen, Raise, Run,
   Set, Switch, Try, Wait` (`dsl.md:168-181`). Complete enough for the whole comparison
   matrix in `comparison.md:31-42`, which shows retries / timeouts / error handling /
   parallel / iterative / subflow / conditional supported by **all seven** engines compared
   (Step Functions, Google Workflows, Argo, BPMN, Prefect, Dagster). That seven-feature
   intersection is the empirical floor.
2. **Sequence by declaration order, with explicit override.** "The task to run next is
   **implicitly the next in declaration order**, or explicitly defined by the `then`
   property" (`dsl.md:226`). Zero ceremony for the common case.
3. **Structured jumps only — the anti-spaghetti rule.**
   > "Flow directives may only redirect to tasks declared **within their own scope**. In
   > other words, they cannot target tasks at a different depth."
   > — `dsl.md:231`, repeated at `dsl-reference.md:1294-1295`

   Four directives total: `continue`, `exit`, `end`, `<task-name>`
   (`dsl-reference.md:1287-1292`).
4. **`switch` with a designated default arm.** "If not set, the case will be matched by
   default if no other case match. Note that there can be **only one** default case, all
   others MUST set a condition." (`dsl-reference.md:1198`).
5. **Priority of Constituencies, written into the spec:**
   > "Authors: people authoring and reading workflows … **If a trade-off needs to be made,
   > always put author's needs above all.** … Author needs come before the needs of
   > operators, which come before the needs of runtime implementors, which come before the
   > needs of specification writers, **which come before theoretical purity**."
   > — `dsl.md:54-67`

   PACT should adopt this verbatim and put it at the top of the spec.

**What does not work — and the proof is the spec's own flagship example.**

`use-cases/multi-agent-ai-content-generation/README.md` is a five-agent content pipeline —
the single closest thing in the corpus to PACT's D20 demo ("a non-technical author builds a
multi-agent system"). It is ~103 lines of YAML written by the working group that authored
the DSL. It contains, verifiably, **five defects**:

**Defect 1 — it is not valid YAML. [executed]**
```
$ python3 -c "…yaml.safe_load(first ```yaml block of README.md)…"
yaml.scanner.ScannerError: mapping values are not allowed here
  in "<unicode string>", line 30, column 30:
            as: $context + { text: .text }
                                 ^
```
That is `README.md:97`. The bare (undelimited, unquoted) jq expression contains a `{ … }`,
and YAML's plain-scalar scanner hits `text: .text` inside it. **The embedded language's
syntax collides with the host language's.** This is §5.3's "no second language in a string
literal" rule, promoted from stylistic objection to hard failure. The spec's `For` example
avoids it only by *quoting*: `output.as: '.pets + [{ "id": $pet.id }]'`
(`dsl-reference.md:719`) — a third spelling, chosen for reasons the author is never told.

**Defect 2 — a type error in the context plane. [executed]** Assume the file were fixed to
parse. `dsl.md:268` is normative: "The result of this runtime expression **replaces** the
workflow's current context". So:
- `README.md:83-87` — `initialize` sets `{prompt: <string>}` and exports `as: .prompt`.
  Context becomes a **string** (the input schema declares `prompt: {type: string}`,
  `README.md:78-79`).
- `README.md:97` — `generateText` exports `as: $context + { text: .text }` — a jq
  `string + object`.
```
$ echo null | jq -c '"hello" + {text:"x"}'
jq: error (at <stdin>:1): string ("hello") and object ({"text":"x"}) cannot be added
```
[executed, jq 1.7]. **Runtime fault on the second task.**

**Defect 3 — the author confused the context plane with the output plane.** `dsl.md`
step 9 is normative: "**The transformed output of the previous task is passed as the raw
input to the next task**". So inside a task, `.` is the *previous task's output*, not the
context. But `evaluateQuality` (`README.md:109-118`) reads `${ .text }` **and**
`${ .image }`, while its predecessor `generateImage` returns only an image (evidenced by
its own export, `$context + { image: .image }`, `README.md:107`). `.text` is therefore
`null` at `README.md:115`. The author wrote `.text` meaning "the thing I put in the
context" — which is what `$context.text` would mean. **Two data planes, one syntax.**

**Defect 4 — a switch with no default arm.** `refineContent` (`README.md:120-128`) has two
conditioned cases and no default. The spec permits a default (`dsl-reference.md:1198`) but
does not require one, and does not define what happens when none matches. The CTK answers
by omission: in `ctk/features/switch.feature:14-25` the "matching case" scenario has three
conditioned arms, **no default and no `then:` on the switch itself** — so per `dsl.md:226`
an unmatched switch *continues to the next task in declaration order*, which in the
idiomatic layout is **the first branch**. A non-matching router silently runs branch one.
(The "implicit default" scenario at `:51-71` avoids this only because the switch there
carries `then: end`.)

**Defect 5 — an unbounded agent refinement loop.** `refine` ends with
`then: evaluateQuality` (`README.md:157`), and `evaluateQuality` leads back to
`refineContent` → `refine`. There is no iteration cap anywhere in the file, and none is
available: `For.while` is "a runtime expression … that must be met for the iteration to
continue" with **no companion limit** (`dsl-reference.md:693`), and `retry.limit` is
optional (`dsl-reference.md:2187`, Required column = `no`). **The specification has no
mandatory termination bound anywhere.**

**And the reason all five shipped:** CI validates only `examples/*.yaml`, non-recursively:
```ts
const examplePath = "../../../examples";
… fs.readdirSync(…, { recursive: false, withFileTypes: true })
  .filter((file) => file.isFile())
  .filter((file) => file.name.endsWith(".yaml"))
```
— `.ci/validation/src/examples.test.ts:23,26-34`, driven by
`.github/workflows/schema-check.yaml:22-51`. The `use-cases/**/README.md` YAML blocks are
never touched. [executed] I scanned **141 YAML blocks** across `dsl.md`,
`dsl-reference.md`, `use-cases/**` and `ctk/features/*`: **2 do not parse** — `dsl.md:741`
and the multi-agent example. All **66** `examples/*.yaml` parse, because those are the ones
CI sees.

Even so, shape validation would not have caught defects 2–5. Those are **data-flow, name-
resolution and termination** properties, and no JSON Schema can express them.

> **Finding, stated as strongly as the evidence supports it: the working group that wrote
> the DSL could not write a correct 100-line multi-agent workflow in it, and their CI could
> not have told them.** That is the strongest available evidence that a multi-plane,
> expression-threaded data model is beyond a non-technical author — and it lands directly
> on PACT's D20 target.

### 4.3 What OAM/KubeVela adds

- **"Application Models Are Not Programming Models."**
  > "An application model describes the *composition* of an application and the topology of
  > its components. It is not concerned with *how* each component is implemented … The Open
  > Application Model offers an application model that does not have any requirements of a
  > programming model."
  > — `protocols/oam-spec/9.design_principles.md:29-33`

  Adopt verbatim as a PACT design principle for the topology/loop IR.
- **"Balance (Elegance): Simple scenarios should be achievable with minimal investment of
  time and energy, but complex scenarios should be accommodated without requiring
  re-platforming."** (`9.design_principles.md:15`) — the precise statement of the "one file
  → full tree" progressive-disclosure requirement (T5, O7.1–O7.3).
- **Three-tier namespace for extensibility:** `core.oam.dev` (runtimes REQUIRED to
  implement), `standard.oam.dev` (RECOMMENDED, portability-maximising), and extension
  namespaces (runtime-specific, MUST NOT use the first two) (`6.traits.md:83-87`). PACT's
  thesis has only *core* and `x-`; **a middle "standard" tier is worth adding** — it gives
  adapters a portability target between "everyone must implement" and "nobody has to",
  which is exactly what a capability lattice (P-2) needs.
- **KubeVela's `if` is the cautionary tale.** Workflow-step conditionals are "executed as
  cue code" with implicit `status` and `inputs` variables
  (`config/kubevela/docs/examples/workflow/app-with-if/README.md:38-44`). Four hazards in
  one example file:
  - a magic sentinel mixed into an expression field: `if: always` (`:30`);
  - **two spellings for the same thing**: `if: status.suspend.timeout` (`:70`) and
    `if: suspend.timeout` (`:75`) — implicit scope elision;
  - bracket escape required for hyphenated names:
    `if: status["notification-1"].succeeded` (`:84`);
  - string concatenation smuggled into a data field:
    `valueFrom: context.name + " message"` (`:110`).

  All four are the accretion smell Crossplane warned about.

### 4.4 Recommendation — PACT control flow

**C1. A closed verb set, chosen once.** Derived from the intersection at
`serverless-workflow/comparison.md:31-42` and the 12 verbs at `dsl.md:168-181`, reduced to
what agent orchestration actually needs (G-2 ≥ 8 topologies, G-3 ≥ 6 loops):

| Verb | Purpose | Covers |
|---|---|---|
| `call` | invoke agent / tool / model / sub-team | pipelines, supervisor dispatch |
| `steps` | run children in declaration order | sequential pipeline |
| `parallel` | run children concurrently; `compete: true` for first-wins | map-reduce, debate, best-of-N |
| `each` | iterate a collection; `while:` guard; **`max_iterations:` required** | ReAct, Reflexion, self-consistency |
| `choose` | ordered conditioned arms + **exactly one mandatory default** | routing, handoff, blackboard dispatch |
| `try` | attempt + typed catch + retry policy with **required `limit`** | fault tolerance |
| `set` | bind a named value into the single data plane | data flow |
| `stop` | terminate this scope with an outcome | halt conditions |

Eight verbs. `wait`, `emit`, `listen` are **not** in the no-code core (they belong to the
runtime seam, D24/D25); if needed they enter as `standard`-tier, not `core`.

**C2. Termination is structural, not advisory.** `max_iterations` is **mandatory** on
`each`; `limit` is **mandatory** on `try.retry`; a `then:` cycle among siblings requires a
declared `max_cycles` on the enclosing scope. Evidence: Serverless Workflow makes all three
optional and its own flagship example diverges (§4.2 defect 5); CEL's entire design bets on
termination (`cel-spec/README.md:16-17`); Dhall's does too (`dhall-lang/README.md:143`). A
loop IR that can diverge turns "an agent that learns" into "an agent that burns budget".

**C3. `choose` must have exactly one default arm, and it is mandatory.** Not "may have"
(`dsl-reference.md:1198`) — *must*. The alternative, demonstrated in the CTK
(`ctk/features/switch.feature:14-25`), is that an unmatched router silently executes the
first branch. Portkey gets this right by throwing (`conditionalRouter.ts:61`); PACT should
get it right at **load** time by requiring the arm to exist.

**C4. Structured jumps only.** Adopt `dsl.md:231` verbatim: a `then:` may only name a
sibling in the same scope. Anything else is a validation error with a two-span diagnostic.

**C5. One data plane.** A single `state` document, plus each step's `result`. No
raw-vs-transformed distinction, no `$context` separate from `$input`, no availability
matrix. Steps read `state.<name>` and write `state.<name>` via `set:` or a step's declared
`output_to:`. This is the direct repudiation of `dsl.md:451-459` and the direct fix for
§4.2 defect 3 — the plane confusion that broke the spec's own example.

**C6. Sequence by declaration order.** `steps:` is an ordered array of named tasks; no
edges required for the common case (`dsl.md:226`). Explicit graph edges are an *optional*
expansion for non-linear topologies (G-2), never required for a pipeline.

**C7. Extension is a *typed node kind*, resolved out-of-tree, never a string of another
language.** A new loop pattern or topology is a `kind:` registered by a definition package
with its own JSON Schema and its own UI hints — the KubeVela definition model
(`design/vela-core/workflow_policy.md:78-95`) minus the CUE-in-a-string, plus Crossplane's
out-of-tree/versioned property (`design-doc-composition-functions.md:181-183`: "Decouple
adding new ways to 'do composition' from the core release cycle"). Escapes to real code
(F-2) remain `ref:`-shaped and *declared*, so they stay analysable — but they are never the
mechanism for expressing a loop.

**C8. Conditions in `choose` and `while` are Tier-0 structured predicates** (§1.7). A
`choose` arm is `{ when: <predicate>, then: <task>, because: <string> }` — byte-for-byte
the shape of `cel.policy.Match{condition, output|rule, explanation}`
(`config/cel-spec/proto/cel/policy/policy.proto:47-59`) and of Portkey's
`{query, then}` + `default` (`conditionalRouter.ts:49-59`).

**C9. Every example in PACT's own documentation is CI-validated, recursively, including
fenced code blocks in Markdown.** Serverless Workflow's `examples.test.ts:26` sets
`recursive: false` and scans one directory; the cost of that single flag is the state of
its flagship use case. PACT's test must extract every fenced `yaml` block from every `.md`
under `docs/` and `examples/`, load it through the *real loader*, and additionally run the
reference and termination checks — not just shape validation, which would have caught only
one of the five defects in §4.2.

---

## 5. YAML vs the alternatives

### 5.1 The constraint set

D2 makes the file tree the native, directly-interpretable form (no build step). D18
requires the *same* files to be written by (a) a hand editor, (b) a form UI, (c) a builder
agent, and (d) reviewed as a git diff. D17 requires everything offline. D4 puts the loader
in Rust.

### 5.2 Scoring the candidates

| Candidate | Hand-edit | Form UI round-trip | LLM-generatable | Git diff | Offline | Rust loader | Verdict |
|---|---|---|---|---|---|---|---|
| **YAML (restricted profile)** | ✔ best-known | ✔ if CST-preserving editor | ✔ best-known by far | ✔ line-oriented | ✔ | ⚠ ecosystem gap (§5.5) | **Adopt** |
| JSON | ✔ but noisy; **no comments** | ✔ | ✔ | ✔ | ✔ | ✔ | Interchange only |
| TOML | ✔ flat; poor for deep trees | ✔ | ⚠ | ✔ | ✔ | ✔ | No |
| CUE | ✘ needs unification model | ✘ (KubeVela wraps it, then generates OpenAPI **with a panic-recover**, `pkg/utils/common/common.go:266-289`) | ✘ | ⚠ | ✔ | ✘ (Go) | No |
| KCL | ✘ Python-like, indentation-significant | ⚠ | ⚠ | ⚠ | ✔ | ✔ (is Rust) | No — but **steal its diagnostics** |
| Pkl | ✘ full language | ⚠ | ✘ | ⚠ | ✔ | ✘ (JVM/GraalVM) | No — but **steal its error rendering** |
| Jsonnet | ✘ 6 field separators | ✘ | ✘ | ⚠ | ✔ | ✘ (C++/Go) | No |
| Dhall | ✘ types/lambdas | ✘ | ✘ | ⚠ | ✔ | ✘ (Haskell) | No — but **steal `normal form`** |
| Go templates over YAML (Helm) | ✘ 61% template lines, 66 hand-computed indents | ✘ | ⚠ | ✘ | ✔ | ✘ | No — and see §3.3 for the cost |

### 5.3 The decisive anti-pattern: a second language inside a string literal

KubeVela's extension mechanism is CUE embedded in a YAML block scalar:
```yaml
spec:
  extension:
    template: |
      parameter: { cmd: [...string] }
      output: { apiVersion: "apps/v1", … }
```
(`config/kubevela/design/vela-core/appfile-design.md:88`, rule stated at `:145`: "The
entire template should be put under `spec.extension.template` as **raw string**"; further
instances at `:153`, `:314`.)

Costs, all observable:
- No schema validation of the embedded text at the YAML layer; the CUE is opaque to every
  YAML tool.
- Positions inside the block scalar must be re-mapped to be reportable.
- CUE idioms leak into the platform-builder's job: `frequency: *"enabled" | "disabled"`
  (`design/vela-core/workflow_policy.md:90`) is how you write "an enum with a default" —
  unwritable by a non-coder.
- The CUE→OpenAPI→form pipeline is fragile enough to need a `recover()`:
  ```go
  defer func() { if r := recover(); r != nil {
      err = fmt.Errorf("invalid cue definition to generate open api: %v", r) …
  ```
  `config/kubevela/pkg/utils/common/common.go:266-289` (again at `:292-295`).
- Crossplane arrived at the same anti-pattern from the other direction with Go templates in
  `input.inline.template` (`design/one-pager-function-go-templating.md:18-24`), and §3.3
  measures where that leads.

**And the new, decisive datum:** the embedded language does not merely resist tooling — it
**collides with the host grammar**. `as: $context + { text: .text }` is a valid jq
expression and an invalid YAML line, and the result is that the flagship multi-agent
example of a CNCF-track specification has never once been parsed (§4.2, defect 1). The
spec's own examples then use four incompatible workarounds (§1.5), of which quoting is the
only correct one and is used inconsistently.

> **PACT rule: no field in a PACT document may contain source text in another language,
> except Markdown (`instructions.md`, skills) and explicitly-typed `ref:` escapes (F-2).**
> Corollary: **Tier-1 CEL, if it ships, must live in a field whose schema type is
> `cel-expression`, must be single-quoted by `pact fmt`, and `pact check` must parse it at
> load time** — never leave it as an unvalidated string (Portkey's `query: z.object({})`,
> §1.2).

### 5.4 YAML's real hazards, and the restricted profile that removes them

YAML 1.1 boolean coercion is a live problem, and implementations defend against it
specifically: KCL has a dedicated grammar test whose *entire content* is `on = "on"` and
whose golden output is `'on': 'on'` — quoted on emit (`config/kcl/tests/grammar/yaml/on/main.k`,
`.../stdout.golden`).

**The `pact.dev/v1` YAML profile (normative):**

| Rule | Why |
|---|---|
| YAML **1.2 core schema** only. `y/yes/n/no/on/off` are **strings**, never booleans | KCL's `on` test; the Norway problem |
| **No tabs.** Two-space indent. Emitted canonically | KCL ships tab/indent error tests (`tests/grammar/syntax/tab/tab_error_{0,1}`, `syntax/indent/indent_error_{0,1}`) |
| **No anchors/aliases (`&`/`*`), no merge keys (`<<`)** | Non-local reads; defeats "the file is what runs"; PACT has `$ref`-by-name instead |
| **No multi-document streams (`---`)** per file | One file = one node; the Expansion Rule already gives multi-node structure via directories |
| **No flow style** for authored content (block style only) | Line-oriented diffs (D18); and flow style is exactly what collided with jq in §4.2 |
| **No implicit sexagesimal / octal / large-int surprises**; durations and sizes are **suffixed strings** (`30s`, `128k`, `4MB`) with a PACT-owned parser | Same coercion class; also makes `context >= 128k` renderable in a form; and avoids `format:` (§2.3) |
| **Keys are `snake_case`, ASCII, `[a-z][a-z0-9_]*`** | No quoting needed; no `status["notification-1"]` bracket escapes (KubeVela `app-with-if/README.md:84`) |
| **Ordered ⇒ array of records with `name:`. Unordered ⇒ map.** Never a list of single-key maps | `kubevela/apis/core.oam.dev/common/types.go:363` ("the type must be array to keep the order"); avoids Serverless Workflow's `- taskName: {…}` double-nesting (`dsl-reference.md:1136-1146`), which is also what makes its error paths read `['do', 0, 'searchStarWarsCharacters']` |
| **Reject duplicate keys** (error, not last-wins) | Silent loss; violates T7/AC-7.1 |
| **Reject unknown keys** with did-you-mean, via a **separate key-check pass** — never `additionalProperties`/`unevaluatedProperties`; `x-` prefixed keys round-trip untouched | AC-1.3; and §2.3's false-diagnosis result |
| Files end with newline; canonical emitter is idempotent (`pact fmt` is a fixed point) | Machine writes must not churn diffs |

### 5.5 The Rust ecosystem gap — a concrete, actionable risk

D18 requires the UI and the builder agent to **write the same files a human hand-edits**.
That requires a **comment- and format-preserving** YAML editor (CST-level), not a
serde-style loader.

Evidence of the gap, from the corpus: KCL — itself a Rust project — **vendors a fork of
`serde_yaml`** at `config/kcl/3rdparty/serde_yaml`, wired in at `config/kcl/Cargo.toml:44`
(`serde_yaml = { path = "3rdparty/serde_yaml" }`). Upstream `serde_yaml`'s own README states
*"(This project is no longer maintained.)"* (`config/kcl/3rdparty/serde_yaml/README.md:10`),
and KCL's note says they "forked the deprecated upstream serde_yaml library and fixed
several critical bugs" (`README.md:14-16`). A grep for `comment` across
`3rdparty/serde_yaml/src/**` returns nothing — it is comment-lossy by construction.

**Recommendation:** PACT's Rust core needs **two** YAML paths:
1. A **CST/lossless path** (positions, comments, blank lines, key order preserved) used by
   the loader for diagnostics and by *every writer* (UI, builder agent, `pact fmt`, learning
   write-backs under T6/D22).
2. A **value path** for canonicalisation into `canonical.json`.

Round-trip must be a tested invariant: `write(read(f)) == f` byte-for-byte for any
conforming file. Without it, the UI surface silently strips the comments a domain expert
wrote to explain their own agent — and D18 collapses to "files or UI, pick one".

### 5.6 Markdown's role

Keep Markdown strictly for **prose that the model consumes**: `instructions.md`, skills,
eval rubric text, `because:` long-form. It must never carry structure PACT parses beyond
optional YAML front-matter. Markdown has no error positions worth reporting and no schema;
structure in Markdown is structure you cannot validate. (Note the corollary from §4.2: YAML
*inside* Markdown is a real authoring surface for documentation, and PACT must therefore
validate its own fenced blocks — C9.)

---

## 6. The schema→form pipeline (D18, surface b)

KubeVela is the only system in the corpus that ships this end-to-end, and its data model is
the specification PACT should copy.

**Generation:** CUE `parameter` block → OpenAPI v3 → form
(`design/vela-core/appfile-design.md:255`; implementation `pkg/utils/common/common.go:266-289`,
`openapi.Config{ExpandReferences: true}`).

**Default widget derivation** (`pkg/utils/schema/ui_schema.go:128-155`) — maps straight onto
PACT's JSON Schema and needs no per-field authoring:

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
| `Description` (`:46`) | JSON Schema has `description`, but not per-surface |
| `UIType` (`:49`) | Widget override |
| `Style.ColSpan` (`:50,96-99`) | Layout |
| `Disable` (`:52`) | Progressive disclosure |
| `Conditions []Condition` (`:60`) | Show/hide by another field's value: `{jsonKey, op ∈ {==,!=,in}, value, action ∈ {enable,disable}}` (`:68-79`), validated at `:82-93` |
| `SubParameterGroupOption` (`:61,102-105`) | Which `oneOf` branch, as a labelled choice |
| `Validate.Immutable` (`:118`) | "cannot be changed twice" — no JSON Schema equivalent |
| `Validate.Options []Option{Label,Value}` (`:115,122-125`) | Enums need **display labels**, not just values |

**One thing not to copy.** KubeVela's condition precedence is documented in a comment block
at `ui_schema.go:53-58`:
> "if all conditions are not matching, the parameter will be disabled / if there are no
> conditions, and disable==false the parameter will be enabled / if one disable action
> condition is matched, the parameter will be disabled / if all enable actions conditions
> are matched, the parameter will be enabled."

Four interacting rules over a list that mixes `enable` and `disable` actions, with an
implicit AND over enables and an implicit OR over disables. Nobody can predict this.
**PACT's `show_when:` is a single Tier-0 predicate with one polarity** — visible iff the
predicate passes — and there is no `action:` field.

**Recommendation.** PACT ships, per schema node, an optional `x-pact-ui` block carrying
exactly: `sort`, `label`, `help`, `widget`, `group`, `show_when` (a Tier-0 structured
predicate — one predicate model serves routing, evals, capability requirements *and* forms),
`immutable`, and `options: [{label, value}]`. Everything else derives from JSON Schema via
the table above. This keeps the form UI a *pure function of schema plus a thin hint layer* —
the property that makes E-3 ("new authoring surface is free") true for the UI as well as the
filesystem.

---

## 7. Cross-cutting: what "no-code" costs, measured

| Concern | Evidence of the cost | PACT mitigation |
|---|---|---|
| Hand-translating another format into the config language is error-prone | KubeVela on its own addons: "This is **hugely error prone** as the CRDs etc. are converted to cue … Addons are not always kept up to date" (`design/vela-core/helm-component.md:28-32`) | D15 ("translate or nothing") is expensive — invest in *mechanical* importers with `ImportReport` (P-3), never hand-ported definitions |
| Expression syntax in user data is an injection vector | "Runtimes must not parse or evaluate expression syntax embedded in workflow input" (`serverless-workflow/dsl.md:387`); Helm violates it with `tpl (toYaml .) $` (`litellm deployment.yaml:33,50`) | Tier-0 predicates are data; Tier-1 CEL evaluates only text from spec files, never from run inputs |
| Errors truncated by default | `cue/parser/interface.go:131`, `cmd/cue/cmd/flags.go:104` | Report all independent errors, always |
| Errors *multiplied* by unions | 65 output units for one typo (§2.2) | Discriminate before validating |
| Errors that are *wrong* | `unevaluatedProperties` reports a bad value as an unknown field (§2.3) | Separate key-check pass |
| Rule provenance invisible | CUE's `field not allowed` with no "says who" | Two-span diagnostics; mandatory `because:` |
| Overlay effects non-local | Pkl spreadsheet semantics (`index.adoc:770-776`); Kustomize merge keys declared nowhere in the tree (§3.4) | No late binding (S6) + declared merge semantics (S3a) + `pact explain` (S7) |
| Templating acquires a test suite the author cannot write | 1,434 test lines vs 839 template lines in one chart (§3.3) | No templating. Structured data + typed node kinds |
| Docs drift from behaviour | OPA's `# METADATA` attaches title/description/authors/related_resources/**schemas** to rules with scope inheritance (`config/opa/v1/ast/annotations.go:20-90`: scopes `package\|rule\|document\|subpackages`, resolved through an `annotationTreeNode`) | PACT's `because:`/`description:` are *fields of the rule*, not comments, and inherit down the tree the same way |
| Docs examples rot | 2 of 141 spec YAML blocks do not parse; CI scans one directory non-recursively (§4.2) | C9: every fenced block in every doc goes through the real loader in CI |

---

## 8. Concrete spec-ready decisions

1. **No author-facing expression language.** Tier-0 structured predicates
   (`{atom, operator, value}` records, implicit AND; `all_of`/`any_of`/`none_of`
   combinators that are **structurally exclusive** with atoms) are the complete no-code
   surface for capability requirements, routing, eval gates, SLO gates and form
   conditionals. Two shipping systems (Crossplane validation, Portkey routing) independently
   bottom out at the same ~11 operators.
2. **Predicate evaluation is three-valued** — `pass | fail | unknown`. An absent benchmark
   figure, or a figure without provenance in `strict` mode, yields `unknown` and its own
   diagnostic; it is never silently `fail`. (Portkey `parseFloat(undefined) ⇒ NaN ⇒ false`.)
3. **Tier-1 restricted CEL** as an optional expert form: macros/arithmetic/string-ops
   disabled, `&&`/`||` lowered to `?:`, all numerics `double`, three-valued lifting, must
   round-trip to Tier 0 where expressible, must be a typed schema field (never an
   unvalidated string). Gated offline by the 2,855-case CEL conformance textproto suite.
4. **Every author-written rule carries a mandatory `because:`.** Enforced by the validator.
   Evidence: Crossplane 50/50 `message=`, CEL-policy `explanation`, KCL check messages —
   and KCL's message-less golden, which is the proof of what happens without it.
5. **JSON Schema for shape only.** No `additionalProperties: false`, no
   `unevaluatedProperties: false`, no `format:`, no `default:` as behaviour. Unknown-key
   detection is a **separate pass** over the closed key set for the discriminated `kind`.
6. **Discriminator-first validation** — never expose a `oneOf` failure to an author.
7. **PACT owns a stable-coded error catalogue**, shipped as in-repo Markdown (air-gapped),
   with two spans, inlined actual value, did-you-mean (levenshtein ≤ 3, dedup, no-op
   suppression), sub-expression value trace, user frames only, and a one-line fix. All
   independent errors every run, with parser cascades collapsed.
8. **A `failtracer` for the resolver.** When a name, capability or benchmark does not
   resolve, emit an OPA-style `… undefined, did you mean …?`. This is the mechanism D11's
   "fail, then recommend" needs.
9. **Six-layer linear overlay** (`built-in → profile → workspace → agent → variant → run`),
   replace-by-default, explicit `merge:`, name-keyed lists, one instance per kind,
   `conflicts_with:` **and** `requires:`, no late binding, and **merge semantics declared in
   the schema per field** (`x-pact-merge`).
10. **Defaults live in profiles, not in the schema.** CI asserts every schema `default`
    validates against its own subschema and equals the profile value.
11. **`pact explain`** (normal form / field provenance incl. merge rule / resolved diff) is a
    required CLI verb.
12. **Eight control-flow verbs**, declaration-order sequencing, **mandatory termination
    bounds** (`max_iterations`, `retry.limit`, `max_cycles`), **mandatory default arm on
    `choose`**, scope-local jumps only, single data plane, out-of-tree typed node kinds for
    extension — never another language in a string.
13. **YAML 1.2 restricted profile** (no tabs/anchors/aliases/merge-keys/multi-doc/flow;
    snake_case keys; suffixed durations and sizes; duplicate keys are errors; `x-`
    round-trips).
14. **Lossless CST YAML I/O in the Rust core**, with `write(read(f)) == f` as a tested
    invariant — the Rust ecosystem does not supply this off the shelf.
15. **`x-pact-ui` hint layer** (sort/label/help/widget/group/`show_when`/immutable/options),
    with `show_when` a single-polarity Tier-0 predicate and **no `action:` field**.
16. **Add a `standard`-tier namespace** between core and `x-` extensions (OAM's three-tier
    model), giving adapters a portability target.
17. **Every fenced YAML block in PACT's own documentation is loaded by the real loader in
    CI**, recursively, and additionally passes the reference and termination checks.

---

## 9. Open questions

Carried forward, with what this pass could and could not settle.

1. **Which Rust CEL?** *Unchanged and re-confirmed:* there is no Rust CEL implementation
   anywhere in the 141-repo corpus. Options: vendor one, run an out-of-process evaluator, or
   write a ~500-line evaluator over the restricted profile. The last removes the protobuf-AST
   dependency entirely, and the 2,855-case conformance suite is available offline to gate a
   *subset* implementation (skip the macro/arithmetic/string-ext files, keep
   `comparisons`, `logic`, `basic`, `fields`, `parse`). **Leaning: write our own, gate on the
   subset, document the exclusions.**
2. **Does Tier 0 actually cover D14's ceiling?** *Still open, and now sharper.* Needs a
   falsification pass: take the 6 loop patterns (AC-5.2) and 8 topologies (AC-5.1) and write
   every `when:` in Tier 0. The known-hard cases are aggregates — "majority vote of N
   verifiers", "best-of-N by score", "stop when the last two evaluations agree". Each is a
   candidate for a **named atom** (`majority_of:`, `argmax_of:`, `converged_for: 2`) rather
   than an expression. Naming them is cheap; a general expression language is not.
3. **Where do SLO predicates live?** `TTFT p95 < 300ms` is a Tier-0 atom, but percentile
   semantics (O4.2) and modality-awareness (D16: voice TTFT ≠ batch E2E) mean the atom needs
   `percentile:` and `modality:` fields. One atom kind with those fields, or several? *Not
   settled here — belongs with `slo-observability.md`.*
4. **Merge semantics for `instructions.md`.** The Expansion Rule makes a Markdown file a
   field value. Replace-by-default (S2) is the consistent answer; skills composition may want
   append. **Recommendation from this pass:** make it explicit and visible —
   `instructions: {merge: replace|prepend|append}` — because §3.4 shows that an undeclared
   merge rule is the defect, not the choice of rule.
5. **Do `x-` blocks participate in overlay?** They must round-trip (AC-1.3), but if two
   layers both set `x-vendor.foo`, PACT does not know the merge semantics. **Proposal
   stands:** `x-` blocks are replaced wholesale at the owning key, never deep-merged.
6. **Error-catalogue localisation.** Pkl externalises 1,210 message strings with nine
   graded variants for a single "property not found". **Recommendation from this pass:**
   commit to an externalised catalogue from day one. Pkl's variant structure
   (`…InScope` / `…InScopeListCandidates` / `…NoHint`) is not localisation, it is *message
   selection by available context*, and retrofitting that at ~200 messages is the expensive
   part — not the translation.
7. **`pact explain --diff` and the change-classification function (D23).** Should the
   blast-radius classifier operate on the *authored* diff or the *resolved* diff? Resolved is
   semantically correct but enormous; authored is reviewable but can miss overlay-mediated
   changes. §3.4 and §3.2 both argue the classifier needs the resolved form — a Kustomize-
   style overlay edit of four lines can change five environment variables. **Leaning:
   classify on resolved, present on authored, and show the resolved delta inline.**
8. **oam-spec is dormant** (last commit 2024-12-24, now ~20 months). Borrowing its
   three-tier namespace and trait rules is fine; borrowing its *governance* as a portability
   argument is not.
9. **[New] What is the non-coder's mental model of "the list I edited"?** S3 says list
   identity is a `name:` key. But a form UI renders a list as rows and a builder agent emits
   one wholesale. The three surfaces disagree about whether the author is *amending* or
   *replacing*. Needs a decision recorded in the spec: **proposal — the UI and the builder
   agent always emit the full list (replace), and `merge: by_key` exists only for
   hand-authored overlays**, so the "spooky action" case is reachable only by someone who
   typed the word `merge`.

---

## Appendix A — reproduction scripts

All run offline against the local corpus. `BASE=/home/bud/ditto/agent-inter-op/research/repos`.

**A.1 — jq type error behind Serverless Workflow defect 2**
```sh
echo null | jq -c '"hello" + {text:"x"}'
# jq: error (at <stdin>:1): string ("hello") and object ({"text":"x"}) cannot be added
```

**A.2 — JSON Schema error explosion**
```python
import yaml, jsonschema, copy
B="$BASE/protocols/serverless-workflow/"
V=jsonschema.Draft202012Validator(yaml.safe_load(open(B+"schema/workflow.yaml")))
wf=yaml.safe_load(open(B+"examples/call-http-query-parameters.yaml"))
assert V.is_valid(wf)
def units(doc):
    n=0
    def walk(e):
        nonlocal n; n+=1
        for c in e.context or []: walk(c)
    for e in V.iter_errors(doc): walk(e)
    return n
k="searchStarWarsCharacters"
d=copy.deepcopy(wf); d["do"][0][k]["cal"]=d["do"][0][k].pop("call"); print(units(d))   # 65
d=copy.deepcopy(wf); d["do"][0][k]["than"]="end";                    print(units(d))   # 64
d=copy.deepcopy(wf); d["document"]["version"]="1.0";                 print(units(d))   # 2
```

**A.3 — YAML-block parse scan + expression-spelling census**
```python
import re, glob, yaml, os
B="$BASE/protocols/serverless-workflow/"
tgts=[B+"dsl.md",B+"dsl-reference.md"]+glob.glob(B+"use-cases/**/*.md",recursive=True)+glob.glob(B+"ctk/features/*.feature")
tot=bad=0
for p in tgts:
    txt=open(p,encoding="utf8",errors="replace").read()
    pat=r'"""yaml\n(.*?)"""' if p.endswith(".feature") else r"```yaml\n(.*?)```"
    for m in re.finditer(pat, txt, re.S):
        tot+=1
        try: yaml.safe_load(m.group(1))
        except Exception as e: bad+=1; print(p, txt[:m.start(1)].count("\n")+1, str(e).split("\n")[0])
print(tot, bad)   # 141 2
# spelling census: regex over ^(-\s*)?(when|while|until|as|from|in|if|condition|set):
# ${...}=6  '${...}'=6  bare .expr=40  '.expr'=23
```

**A.4 — Helm chart density**
```sh
cd $BASE/routing/litellm/helm/litellm-helm
cat templates/*.yaml templates/*.tpl | wc -l          # 839
cat templates/*.yaml templates/*.tpl | grep -c '{{'   # 513
wc -l < values.yaml                                   # 456
cat tests/*.yaml | wc -l                              # 1434
grep -o 'nindent [0-9]*' templates/*.yaml | wc -l     # 66
```

**A.5 — Crossplane CEL rule / message census**
```sh
cd $BASE/config/crossplane
grep -rn "XValidation" apis/ | wc -l                  # 50
grep -rn "XValidation" apis/ | grep -c "message="     # 50
```

**A.6 — CEL conformance suite size**
```sh
cd $BASE/config/cel-spec/tests/simple/testdata
ls *.textproto | wc -l                                # 30
grep -h "^ *name:" *.textproto | wc -l                # 2855
```
