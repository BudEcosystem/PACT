# PACT Research Stream — Filesystem / File-Based Agent & Prompt Definition Prior Art

**Stream:** `filesystem-prior-art`
**Date:** 2026-07-26 · **Revised 2026-08-07 (v2)**
**Charter:** survey `research/repos/filedef/*`, `research/repos/protocols/agents-md`,
`frameworks2/dify`, `frameworks2/langflow`; extract exact file format, frontmatter schema,
discovery rules, composition/inheritance model, versioning story — with `file:line`.
Then answer: **is there a defensible general rule that unifies "a directory is a field"?**
Deliver a verdict on Thesis **T5 (the Expansion Rule)** and the normative algorithm it needs.

**Evidence discipline.** Every claim below is either (a) cited to `path:line` in the local
corpus, (b) an **[EMPIRICAL]** result from a command I ran on this machine (shown), or
(c) explicitly marked **[INFERRED]**. Nothing is asserted from memory. Where a document
would disagree with source, I read source.

---

## v2 revision note — what is new since 2026-07-26

The v1 survey (everything below §1) was re-verified on 2026-08-07 and **all of its
load-bearing citations still hold**; the only drift is that Eve's slot table has grown
from 17 to **18** members (`vercel-eve/packages/eve/src/discover/filesystem.ts:40-57`),
which is itself the argument against hand-maintained slot tables. Four things are new:

- **§2.16 — Next.js App Router**, which was in the corpus at
  `research/repos/filedef/nextjs-app-router` (it is the Next.js monorepo, not a sample app)
  and was **missed entirely by v1**. It is the largest-deployment "a directory is a field"
  system in existence, it has all three of the directory sigils PACT lacks, and it carries
  a *documented production 404 caused by collation sort order*.
- **§4.7 — Kubernetes `listType`/`listMapKey`**, the missing precedent for v1's own
  recommendation that merge strategy be a schema annotation rather than an `if`.
- **§5A — 17 adversarial trees run against the *shipped* PACT loader** (`target/debug/pact`,
  this repo, this machine). v1 could only reason about what the spec should say; v2 measures
  what the implementation does. Five defects were found, two of them blocking.
- **§6/§7 updated verdict**, now scored against the implementation rather than against a
  proposal.

---

## 0. Executive summary — the results that change PACT's design

### 0.1 From the v1 survey (re-verified 2026-08-07)

1. **Vercel Eve's slot table is real, closed, and hardcoded — verified.** `AgentRootEntryKind`
   is now an **18**-member string-literal union and `classifyAgentRootEntry` is a chain of
   `name === "…"` comparisons (`vercel-eve/packages/eve/src/discover/filesystem.ts:40-57`,
   `:120-205`). It gained a member since v1 without the rule changing — which is the cost
   T5 exists to remove. **T5's premise is confirmed.**

2. **Nobody in this corpus has a general rule; everybody has an ad-hoc rule, and they
   contradict each other.** Two implementations of the *same* Agent Skills concept invert
   override precedence (goose: project-first-wins, `goose/crates/goose/src/skills/mod.rs:296-322`
   + `:460-485`; cline: remote>global>project last-wins, `cline/apps/vscode/src/core/context/instructions/user-instructions/skills.ts:211-268`).
   Two implementations of the *same* `.prompt` format disagree on how `a.b.c.prompt`
   parses (dotprompt `js/src/stores/dir.ts:149-160` → name `a.b`, variant `c`;
   genkit `js/ai/src/prompt.ts:846-850` → name `a`, variant `b`, `c` dropped).
   **This is the strongest possible argument for PACT specifying one normative loader.**

3. **The general rule exists and it is not new — it is CUE's.** A package is the
   unification of all files in a directory (`config/cue/doc/ref/spec.md:3163-3175`), and
   unification is "commutative, associative, and idempotent. As a consequence, order of
   evaluation is irrelevant" (`config/cue/doc/ref/spec.md:671-676`, verbatim, re-read
   2026-08-07). That is *exactly* "a directory is a field", made sound by choosing a
   **conflict-detecting order-independent merge** instead of last-wins override. **T5 is
   sound if and only if PACT adopts unification-style merge for unordered fields and
   forbids the directory form for ordered fields unless order is carried in-band.**

4. **The single largest concrete risk to `AC-1.4` (byte-identical `canonical.json`) is not
   the Expansion Rule — it is YAML.** **[EMPIRICAL]** PyYAML (`yaml.safe_load`) parses
   `no: value` → `{False: 'value'}`, `on: third` collides with `yes: other` into one key,
   and `version: 1.10` → the float `1.1`. Rust's `serde_yaml` implements only YAML 1.2 core
   booleans (`serde_yaml-0.9.34/src/de.rs:932-938`), so the *same file* yields *different
   documents* in PACT's Rust core (D4) versus a Python adapter/eval provider (D4, D6).

### 0.2 New in v2 — the five results that change the design now

5. **The ordering rule is settled by a natural experiment inside one codebase.** Next.js
   sorts discovered paths with a plain `pathnames.sort()` — UTF-16 code-unit order,
   deterministic, locale-free (`nextjs-app-router/packages/next/src/lib/recursive-readdir.ts:178-180`).
   It *also* sorts manifest entries with `a.localeCompare(b)` in `compareAppPaths`
   (`.../shared/lib/router/utils/app-paths.ts:64-70`). Only the second one has a bug, and
   the bug is **documented in the function's own docstring**: "route group prefixes like
   `(group)` (char code 0x28) sort before `@` (0x40), causing the children page to sort
   first instead of last and leading to a **manifest mismatch / 404** in webpack dev mode"
   (`app-paths.ts:58-63`). Same repo, same team: the code-unit sort has no reported ordering
   defect; the collation sort shipped a 404. Eve (`grammar.ts:176`) and roo-code
   (`custom-instructions.ts:171-175`) both use `localeCompare`. **"Order by code point, never
   by collation" is now evidenced, not merely argued.**

6. **Every mature filesystem-as-config system grows a *sigil alphabet*, and PACT has not
   reserved one.** Next.js has exactly three directory sigils, each a closed one-character
   rule: `(group)` = "organise without naming" (`shared/lib/segment.ts:7-10`), `@slot` =
   "this directory is a *named field*, not a path segment" (`segment.ts:12-14`,
   `build/file-classifier.ts:13-25`), `_private` = "not part of the document at all"
   (`build/route-discovery.ts:99`). PACT has half-claimed `_` (for `_index` self files) and
   claims a leading-`NN-` ordinal, and has reserved nothing else. **[EMPIRICAL §5A.3]** a
   `_drafts/` folder beside `agent.yaml` is a hard `schema/unknown-field` error whose fix
   text says "Remove it", and `.pactignore` only rescues it when placed *in the same
   directory*. Adding grouping later changes identity, so the alphabet must be reserved in
   `v1` or never.

7. **[EMPIRICAL — BLOCKING] PACT silently renames agents whose folder begins with digits.**
   `agents/2024-audit/agent.yaml` loads cleanly and `pact discover` reports the agent's
   public identity as `pact:audit`. `split_ordinal` (`crates/pact-loader/src/policy.rs:379-396`)
   strips an `NN-`/`NN_` prefix from **every** stem, ordered field or not, so the in-band
   ordering convention steals a namespace from every unordered map — including `agents/`,
   `team:`, `remembers:`, `variants:`. Two such agents (`2024-audit`, `2025-audit`) collide
   into one key and the workspace refuses to load with advice that says the names "differ
   only by capitalisation", which they do not. A silent rename of a published identity
   violates T7 and AC-7.1.

8. **[EMPIRICAL — BLOCKING] A symlinked *self file* is followed outside the workspace and
   reported as a clean load.** `agents/desk/agent.yaml → /outside/evil.yaml` yields
   `OK — … loaded cleanly (9 settings)` with **zero warnings**, and `pact discover` returns
   the outside file's `name`/`description` under `pact:desk`. The `loader/symlink-skipped`
   refusal is applied to ordinary field entries and to whole directories (verified, §5A.13,
   §5A.17) but not to the self-file branch, because `Policy::is_self_file` is consulted
   before the symlink check (`crates/pact-loader/src/lib.rs:826-845`). The loader's own
   module doc asserts the opposite invariant — "A spec tree is a supply-chain surface and a
   link can point anywhere, so the answer is the same at the top of an ordinary folder … and
   inside an attachment folder" (`lib.rs:141-154`).

9. **[EMPIRICAL] PACT has two different case-equality functions and the disagreement is
   author-visible.** Field identity uses `fold_key` = NFC ∘ full-Unicode `to_lowercase`
   (`lib.rs:986-989`); self-file detection uses `eq_ignore_ascii_case`
   (`policy.rs:326-330`). A directory `CAFÉ/` containing `café.yaml` therefore does **not**
   recognise its self file: the agent is reported as missing `description` *and*
   `instructions` even though the author wrote both, and is told to create `agent.yaml`
   (§5A.11). One rule, two functions.

**What is already right and should be defended:** duplicate field keys, file-form ⊕
directory-form collisions, ordinal ties, NFC/NFD sibling collisions, non-UTF-8 bytes in a
text slot and >32-level nesting are **all hard errors with named rules and fixes**
(§5A.1, §5A.2, §5A.5, §5A.9, §5A.12, §5A.15). On the failure modes v1 predicted, the
implementation scores 6/9. The three it misses are §0.2 items 7, 8 and 9.

---

## 1. Method and corpus

| Path | Systems read |
|---|---|
| `research/repos/filedef/` | prompty, dotprompt, genkit, promptl, goose, skills-anthropic, continue, aider, opencode, cline, roo-code |
| `research/repos/protocols/agents-md` | AGENTS.md convention + site copy |
| `research/repos/frameworks2/dify`, `.../langflow` | low-code YAML/JSON DSLs |
| `research/repos/frameworks/vercel-eve` | **the direct precedent for T5** (thesis §0.3) |
| `research/repos/config/{cue,pkl}` | merge/inheritance formal semantics |
| `research/repos/protocols/oci-image-spec` | canonicalisation / content addressing |
| `research/repos/eval/phoenix/kustomize`, `routing/litellm/helm` | Kustomize / Helm layout as used in the wild |

**Not in the local corpus:** Kustomize source, Helm source, Nix, Hugo, Jekyll, Kubernetes
apimachinery (`patchMergeKey`). I found *usages* of Kustomize and Helm and cite those;
I make **no** evidentiary claims about Nix, Hugo, or Jekyll internals because I could not
read their source offline, and the brief forbids network use for locally-available things
and forbids memory claims. Where their pattern is relevant I state it as a structural
observation about the artefacts I *can* see (`kustomization.yaml`, `Chart.yaml`).

---

## 2. System dossiers

### 2.1 Prompty (Microsoft) — `filedef/prompty`

**The most rigorously specified file format in the corpus.** `spec/spec.md` is 3,916 lines of
MUST/SHOULD/MAY (`spec/spec.md:142-152`) with executable conformance vectors in
`spec/vectors/{parse,load,render,process,wire,agent,harness}_vectors.json`.

| Aspect | Finding | Evidence |
|---|---|---|
| File form | Single `.prompty` file: YAML frontmatter + markdown body. Body becomes `instructions`. | `spec/spec.md:156-171` |
| Delimiters | `---` **or** `+++`; opening and closing need not match | `spec/spec.md:159`, `:198-199` |
| Split contract | Normative regex `^\s*(?:---|\+\+\+)(.*?)(?:---|\+\+\+)\s*(.+)$`, dotall+multiline, **plus 4 normative test vectors as tie-breakers** | `spec/spec.md:180-223` |
| Malformed handling | Opening delimiter with no close → **MUST raise `ValueError`** (fail-closed) | `spec/spec.md:195-196`, `:940-949` |
| Frontmatter schema | `name, displayName, description, metadata, model, inputs, outputs, tools, template` | `spec/spec.md:230-240` |
| Unknown keys | **"MUST NOT raise an error for unknown properties"** (permissive) | `spec/spec.md:242-243` |
| Value-level expansion | `model: gpt-4` ≡ `model: {id: gpt-4}`; `template: jinja2` ≡ full object; `inputs.X: Jane` ≡ `{kind: string, default: Jane}`; full table at §4.4 | `spec/spec.md:249-258`, `:331-347`, `:358-373`, `:927-938` |
| **File reference** | `${file:relative/path}` resolves a field's value **from another file** | `spec/spec.md:510-524` |
| Reference typing | `.json` → JSON parse; `.yaml`/`.yml` → YAML parse; **all other extensions → raw text** | `spec/spec.md:514-516` |
| Reference security | MUST canonicalise; MUST reject absolute paths, `..` traversal, symlink escapes outside the prompt dir; host MAY add roots; **"`.prompty` frontmatter MUST NOT be able to grant itself additional allowed file roots"** | `spec/spec.md:518-524` |
| Reference scope | Resolved in **all** string values recursively, not just top level | `spec/spec.md:526-528` |
| Env reference | `${env:VAR}` (fail if unset), `${env:VAR:default}` | `spec/spec.md:498-508` |
| Composition | `kind: prompty` tool → one `.prompty` invokes another, `mode: single \| agentic` | `spec/spec.md:433-457` |
| Modalities | Property kinds include `image`, `file`, `audio`, `thread` ("rich kinds") | `spec/spec.md:313-329` |
| Versioning | **None in the format.** `metadata` is a free dict "(authors, tags, version, etc.)" — version is convention only | `spec/spec.md:235` |
| Loading algorithm | Fully normative pseudocode: resolve → read → split → resolve refs → shorthand expand → inject kind → typed load | `spec/spec.md:844-911` |
| Dotenv | Library **MUST NOT** auto-load `.env`; real env wins over `.env` | `spec/spec.md:913-925` |

**Why this matters to PACT.** `${file:…}` is the closest thing in the corpus to the Expansion
Rule's "field ← file" direction, and it is the *only* one with a written security model.
PACT's Expansion Rule should be read as "`${file:}` generalised to directories, made
implicit by naming convention". Prompty's extension→parser rule (`.json`/`.yaml`/else-raw)
and its containment rules are directly transplantable.

**Divergence from PACT.** Prompty is *permissive* on unknown keys (`:242-243`); PACT's
`AC-1.3` is *strict* (reject with a fix suggestion). Both are defensible; PACT's strictness
is only tenable because it also has `x-` extension namespaces. Note prompty has no
`x-`-equivalent, which is *why* it had to be permissive.

---

### 2.2 Dotprompt (Google) — `filedef/dotprompt`

| Aspect | Finding | Evidence |
|---|---|---|
| File form | `.prompt` file, YAML frontmatter + Handlebars body | `js/src/parse.ts:67-68` |
| Frontmatter regex | `/^(?:(?:#[^\n]*|[ \t]*)\n)*---\s*(?:\r\n|\r|\n)([\s\S]*?)(?:\r\n|\r|\n)---\s*(?:\r\n|\r|\n)([\s\S]*)$/` — **anchored to document start**, tolerates leading `#` license headers and blank lines, handles CR/LF/CRLF | `js/src/parse.ts:64-68` |
| Reserved keys | `config, description, ext, input, model, name, output, raw, toolDefs, tools, variant, version` (kept sorted) | `js/src/parse.ts:99-113` |
| Extension namespace | Any **dotted** top-level key `ns.field: v` → `ext: {ns: {field: v}}`, **one level deep only** | `js/src/parse.ts:167-184`, `:221-228` |
| **Silent drop** | A top-level key that is neither reserved nor dotted is not copied into the pruned metadata — only `raw` retains it, with no diagnostic | `js/src/parse.ts:221-229` |
| **Fail-open parse** | YAML error → `console.error` and **the whole source becomes the template body** | `js/src/parse.ts:230-233` |
| Schema DSL | *Picoschema* — `field?: type, description` compact schema; supports scalars, objects, arrays, enums, `any`, wildcards `(*)`, named-schema refs; CRLF covered by spec test | `spec/picoschema.yaml:25`, `:148-171`, `:171-198`, `:273-295`, `:318-358`, `:359-410`, `:410` |
| Partials | Filename prefix `_` ⇒ partial, referenced `{{> name}}`; nesting supported | `js/src/stores/dir.ts:53-55`, `:172-174`; `spec/partials.yaml:22-72` |
| Directory → name | Subdirectory becomes part of the logical name: `foo/bar` | `js/src/stores/dir.ts:56-58`, `:250-256` |
| Variants | `name.variant.prompt`; **variant = last dot segment**, name = everything before | `js/src/stores/dir.ts:140-161` |
| **Versioning (good)** | `version = sha1(content).slice(0,8)`; `load()` with a requested `version` **errors on mismatch** | `js/src/stores/dir.ts:100-102`, `:379-386` |
| Path safety | `verifyPathContainment` on load/save/delete; `scanDirectory` also re-checks containment | `js/src/stores/dir.ts:114-121`, `:196-204` |
| Discovery | Recursive scan for `*.prompt`; malformed names are `console.warn`-skipped, not errors | `js/src/stores/dir.ts:190-221`, `:267-274` |

**Failure mode: overloaded delimiter.** Because `.` separates both name segments and the
variant, the prompt logically named `a.b` is **unreachable** without also supplying a
variant — `parsePromptFilename("a.b.prompt")` returns `{name: "a", variant: "b"}`
(`js/src/stores/dir.ts:152-160`). A single character carries two meanings.

---

### 2.3 Genkit (Google) — `filedef/genkit`

Genkit consumes dotprompt but re-implements folder discovery, and **disagrees with the
dotprompt reference store**:

| Aspect | Finding | Evidence |
|---|---|---|
| Discovery root | `./prompts` by default, recursive | `js/ai/src/prompt.ts:768-777` |
| Recursion | Directory ⇒ recurse; subdir becomes name prefix | `js/ai/src/prompt.ts:788-818` |
| Partials | `_` prefix ⇒ `definePartial` (registered **globally by bare name**, prefix stripped, subdir *not* included) | `js/ai/src/prompt.ts:792-803` |
| Variant parse | `name.split(".")`; `name = parts[0]`, `variant = parts[1]`; **prefix (subdir path) is included in `name` before the split** | `js/ai/src/prompt.ts:844-850` |
| Registry key | `ns/name.variant` — one flat string carrying three concepts | `js/ai/src/prompt.ts:959-961` |
| Ordering | `readdirSync` order, unsorted | `js/ai/src/prompt.ts:785-788` |

**Verified cross-implementation divergence (same format, two Google implementations):**

| Input | dotprompt `DirStore` | genkit `loadPrompt` |
|---|---|---|
| `a.b.c.prompt` | name `a.b`, variant `c` | name `a`, variant `b`, **`c` silently lost** |
| `sub.dir/x.prompt` | name `sub.dir/x` | prefix `sub.dir/` + `x` → split on first `.` → name `sub`, variant `dir/x` |
| partial `sub/_p.prompt` | name `sub/p` | registered as bare `p` — **collides across subdirectories** |

*Evidence:* `dotprompt/js/src/stores/dir.ts:149-160` vs `genkit/js/ai/src/prompt.ts:844-850`
and `:792-803`.

This is the single most important negative result in the survey: **encoding structured
metadata in filenames with an overloaded delimiter is not implementable consistently even
by one vendor.**

---

### 2.4 PromptL (Latitude) — `filedef/promptl`

Single-file, frontmatter + XML-ish message tags (`<user>`, `<system>`), plus the only
first-class **document reference graph** in the corpus.

| Aspect | Finding | Evidence |
|---|---|---|
| Reference syntax | `<prompt path="..." param=... />` | `src/compiler/scan.ts:551-585` |
| Path attribute | Must be a *literal* attribute (not templated) | `src/compiler/scan.ts:554`, `:576-579` |
| **Cycle detection** | Per-path visited list; re-entry emits `circular-reference` | `src/compiler/scan.ts:587`, `:599-602`; `src/error/errors.ts:201-204` |
| **Depth limit** | `REFERENCE_DEPTH_LIMIT = 50` | `src/constants.ts:25`; `src/compiler/scan.ts:567-570` |
| Parameter contract | Every parameter the referenced doc declares **must** be supplied as an attribute, else `reference-missing-parameter` | `src/compiler/scan.ts:633-640`; `src/error/errors.ts:209-212` |
| Error propagation | Child `reference-error`/`circular-reference` re-raised at the referencing node with position | `src/compiler/scan.ts:641-653` |
| **Composed versioning** | `hash = sha256(rawText ‖ referencedHashes…)` — the hash of a document **includes** the hashes of everything it references | `src/compiler/scan.ts:170-172`, `:655` |
| Reference resolution | Injected `referenceFn(path, fromPath)` — the *host* owns filesystem access; the compiler is pure | `src/compiler/types.ts:10`, `src/compiler/scan.ts:604-607` |
| Missing resolver | Explicit `missing-reference-function` error rather than silent no-op | `src/error/errors.ts:197-200` |

**Directly transplantable to PACT:** the recursive content hash (`:170-172`) is precisely
what `pact.lock` needs so that a lockfile digest changes when a *transitively referenced*
file changes; and injecting the resolver keeps the loader testable offline (D17).

---

### 2.5 Agent Skills — `filedef/skills-anthropic` + five independent implementations

**The spec itself is not in the corpus.** `spec/agent-skills-spec.md:1-3` is a three-line
redirect to `https://agentskills.io/specification`. The normative content is therefore
only observable through implementations, and they disagree. This is itself a finding:
*the most widely-adopted filesystem agent format has no locally-resolvable specification*,
which is disqualifying under D17 (air-gapped).

**The de-facto format** (from `template/SKILL.md:1-6` and the 17 shipped skills):

```
skill-dir/
  SKILL.md          # YAML frontmatter: name, description (+ license, metadata seen in the wild)
  <anything else>   # scripts/, references/, assets/, *.md, *.py, *.pdf …
```

Observed frontmatter keys beyond `name`/`description`: `license`
(`skills/pdf/SKILL.md:4`). Binary payloads ship inside skill directories
(`skills/theme-factory/theme-showcase.pdf`).

#### Implementation comparison (all `file:line` verified)

| Behaviour | **goose** | **cline** | **continue** | **opencode** | **Eve** |
|---|---|---|---|---|---|
| Marker file | `SKILL.md`, matched exactly | `SKILL.md` exact | `SKILL.md` exact | `SKILL.md` (from remote index) | `skill.md` **case-insensitively** |
| Evidence | `goose/…/skills/mod.rs:414` | `cline/…/skills.ts:172` | `continue/core/config/markdown/loadMarkdownSkills.ts:63-65` | `opencode/…/skill/discovery.ts:68-73` | `vercel-eve/…/discover/filesystem.ts:292` |
| Search depth | **fully recursive** from each root | **one level** (immediate subdirs only) | recursive `walkDir` | index-driven | package dir |
| Evidence | `mod.rs:405-418` | `skills.ts:139-166` | `loadMarkdownSkills.ts:36-40` | `discovery.ts:68-76` | `filesystem.ts:281-315` |
| Identity | **frontmatter `name`**; dir name only as fallback when frontmatter absent | **frontmatter `name` MUST equal directory name**, else skill is rejected | frontmatter `name` (zod `min(1)`) | derived from path | package dir name |
| Evidence | `mod.rs:235-248`, `:334-343` | `skills.ts:193-196` | `loadMarkdownSkills.ts:13-16` | — | — |
| Name charset | `[a-z0-9-]`, ≤64, no leading/trailing `-` | unconstrained | unconstrained | unconstrained | unconstrained |
| Evidence | `mod.rs:74-100` | — | — | — | — |
| Precedence | **project first, first-wins** | **remote > global > project, last-wins** | flat list, no dedup | last-wins by map assignment | — |
| Evidence | `mod.rs:296-322` + `:460-485` | `skills.ts:211-218`, `:254-268` | `loadMarkdownSkills.ts:44-105` | `config/agent.ts:29` | — |
| Roots scanned | `.agents/skills`, `.goose/skills`, `.claude/skills` (project) then `~/.agents/skills`, config dir, `~/.claude/skills`, `~/.config/agents/skills`, plugin dirs | `.clinerules/skills`, `.cline/skills`, `.claude/skills`, `.agents/skills` (project) then `~/.cline/skills`, `~/.agents/skills` | `.continue/skills`, `.claude/skills` (+ global) | `.opencode` chain | `skills/` under agent root |
| Evidence | `mod.rs:296-322` | `cline/…/storage/skill-directories.ts:5-10`, `:30-40` | `loadMarkdownSkills.ts:21-42` | `opencode/…/config/paths.ts:24-42` | `filesystem.ts:186-188` |
| Nested skills | Inner `SKILL.md` dirs excluded from the outer skill's supporting files | n/a (non-recursive) | not excluded — inner files listed | n/a | `scripts`/`references`/`assets` classified |
| Evidence | `mod.rs:440` | — | `loadMarkdownSkills.ts:76-81` | — | `filesystem.ts:293-305` |
| Extra metadata | Nested `metadata:` mapping (explicitly to avoid collision with reserved keys, citing the spec) | `disabled: true` toggled **by writing the file** | none | — | — |
| Evidence | `mod.rs:30-36` | `cline/…/skills.ts:28-56` | — | — | — |

**Sub-findings worth carrying into PACT:**

- **goose's ordering is nondeterministic.** `walk_files_recursively` iterates
  `std::fs::read_dir(...).flatten()` with **no sort** (`mod.rs:388-402`), and dedup is
  first-wins on a `HashSet<String>` (`mod.rs:433-451`, `:466`). Two `SKILL.md` files with
  the same `name` under one root resolve by **inode/directory order**, i.e. by how the
  files happened to be created. Contrast `local_recipes.rs:39-45`, where goose *does*
  `sort()` + `dedup()` the recipe search paths.
- **goose does protect against symlink cycles properly**: canonicalised `visited_dirs`
  set (`mod.rs:379-385`). This is the correct technique; roo-code's depth cap is not
  (see §2.10).
- **cline handles the UTF-8 BOM explicitly** because Windows Notepad broke frontmatter
  detection — with an upstream issue reference (`cline/…/frontmatter.ts:38-42`, citing
  `cline/cline#12151`).
- **cline pins YAML to the JSON schema** (`yaml.JSON_SCHEMA`, `frontmatter.ts:52`),
  which removes YAML 1.1's `yes/no/on/off` booleans. This is the correct mitigation for
  the hazard in §5.3.
- **cline's frontmatter parse is fail-open** (`frontmatter.ts:51-58`), but it *returns*
  `parseError` so callers can decide; `updateSkillMarkdownDisabledState` refuses to
  rewrite a file whose frontmatter failed to parse, precisely to avoid corrupting it
  (`skills.ts:36-40`).

---

### 2.6 Goose — `filedef/goose` (recipes, subrecipes, skills, custom agents)

Goose is the closest thing in the corpus to PACT's target runtime, so its shape is
load-bearing for D2/D3/G6.

#### 2.6.1 Recipes

| Aspect | Finding | Evidence |
|---|---|---|
| File form | **Single** `.yaml` or `.json` file; no directory form | `crates/goose/src/recipe/mod.rs:25` |
| Required fields | `title`, `description`; `version` defaults to `"1.0.0"` | `recipe/mod.rs:41-49`, `:27-29` |
| Semantic constraint | At least one of `instructions` / `prompt` — checked at validate time, not by the type | `recipe/validate_recipe.rs:69-87` |
| Fields | `instructions, prompt, extensions, settings{provider,model,temperature,max_turns}, activities, author, parameters, response.json_schema, sub_recipes, retry` | `recipe/mod.rs:50-83`, `:95-114` |
| Composition | `sub_recipes: [{name, path, values, sequential_when_repeated, description}]` — **path reference, not inline** | `recipe/mod.rs:116-124` |
| Discovery | Search dirs: `.`, `$GOOSE_RECIPE_PATH` (`:`/`;` split), `<config>/recipes`, `./.goose/recipes`, `./.agents/recipes`, `~/.agents/recipes` — canonicalised, **sorted, deduped** | `recipe/local_recipes.rs:21-46` |
| Resolution | Name without extension ⇒ try `<name>.yaml` then `<name>.json` in each dir, **first hit wins**; error lists every searched dir | `recipe/local_recipes.rs:48-82`, `:106-119` |
| Listing | Non-recursive `read_dir`, unsorted, per-file parse errors logged and skipped | `recipe/local_recipes.rs:121-152` |
| **Templating** | MiniJinja over the **raw file text before YAML parsing**; `{% extends %}` / `{% include %}` supported | `recipe/template_recipe.rs:92-116`, `:165-168` |
| Template loader | `Path::new(recipe_dir).join(name)` with **no containment check** | `recipe/template_recipe.rs:124-140` |
| Template hacks | `: ""` rewritten to `: ''` to survive MiniJinja escaping; `{{…}}` MiniJinja cannot parse is wrapped in `{% raw %}` | `recipe/template_recipe.rs:99-103`, `:15-20`, `:66-87` |
| Undefined vars | `UndefinedBehavior::Strict` at render, `Lenient` at parse | `recipe/template_recipe.rs:110`, `:173` |
| Validation | Declared `parameters` must cover the template's undeclared variables; `response.json_schema` validated with `jsonschema` | `recipe/validate_recipe.rs:11-20`, `:22-27` |
| Versioning | `version` is a semver *string* on the file format, never checked against a supported range in the loader I read | `recipe/mod.rs:27-29`, `:41-44` |
| Path handling | `~` expansion (Unix `~/`, Windows `~\`), canonicalisation, `parent_dir` captured for relative resolution | `recipe/read_recipe_file_content.rs:12-62` |

**Two findings for PACT:**

- **[INFERRED — code path read, not executed] Path traversal in the recipe template loader.**
  `env.set_loader(move |name| { let path = Path::new(recipe_dir).join(name); fs::read_to_string(&path) })`
  (`template_recipe.rs:124-140`) applies no containment check, so
  `{% include "../../../etc/passwd" %}` resolves outside the recipe directory. Compare
  prompty's explicit MUST-reject rules (`prompty/spec/spec.md:518-524`). **PACT's loader
  must enforce root containment on every include/reference, uniformly.**
- **Text templating a structured format is structurally fragile.** The `{% raw %}` and
  `: ""` → `: ''` workarounds (`template_recipe.rs:15-20`, `:99-103`) exist only because
  the template engine runs *before* the YAML parser and prompt bodies legitimately contain
  braces and quotes. **PACT must template values after parsing, not file text before it.**

#### 2.6.2 Frontmatter parsing (shared by skills, projects, agents)

```rust
// goose/crates/goose/src/sources.rs:20-32
let parts: Vec<&str> = content.split("---").collect();
if parts.len() < 3 { return Ok(None); }
let yaml_content = parts[1].trim();
let body = parts[2..].join("---").trim().to_string();
```

Naive `split("---")` with **no line anchoring**. Any document containing two `---`
substrings anywhere — including inside a word, a code fence, or a markdown horizontal
rule — is treated as having frontmatter. Contrast prompty's anchored regex + normative
vectors (`prompty/spec/spec.md:180-223`) and cline's `/^---\r?\n…/` (`frontmatter.ts:44`).

#### 2.6.3 Source types

`SourceType` = `Skill | BuiltinSkill | Recipe | Subrecipe | Agent | Project`
(`crates/goose-sdk-types/src/custom_requests.rs:1332-1350`). Only
`Skill | Project | Agent` are mutable through the ACP CRUD surface
(`sources.rs:34-41`). Markdown-backed sources use a **flattened** frontmatter model
(`#[serde(flatten)] properties: HashMap<String, Value>`, `sources.rs:59-67`) — i.e. goose
puts unknown keys in a sibling bag, dotprompt puts dotted keys in `ext`, opencode puts
unknown keys in `options`. Three different answers to the same question.

---

### 2.7 Vercel Eve — `frameworks/vercel-eve` (the direct T5 precedent)

**This is the system PACT's Expansion Rule generalises, so I read it closely.**

#### The slot table is closed and hardcoded — confirmed

`AgentRootEntryKind` (`packages/eve/src/discover/filesystem.ts:36-56`) is a 17-member
union. `classifyAgentRootEntry` (`:120-205`) is a literal `if` chain:

- **Files:** `agent.{cts,mts,cjs,mjs,ts,js}`, `instructions.md`, `instructions.{…}`,
  `system.md`, `system.{…}` — everything else is `"unknown"` (`:122-152`).
- **Directories:** `channels`, `connections`, `extensions`, `hooks`, `instructions`,
  `lib`, `skills`, `sandbox`, `tools`, `schedules`, `subagents` — everything else is
  `"unknown"` (`:154-203`).
- Ignored: `.eve`, `.next`, `.output`, `.vercel`, `node_modules` (`:23-29`).

A **second, different** table exists for subagents (`classifyLocalSubagentEntry`, `:208-278`):
no `channels`, no `extensions`, and `schedules` is explicitly `"invalid-schedules-directory"`.
A **third** for skill packages (`:281-315`), a **fourth** for the `skills/` directory
(`:318-336`). Four hand-maintained tables. This is exactly the cost T5 proposes to remove.

#### Eve's answer to "file form vs directory form"

`discoverInstructionsSource` (`src/discover/grammar.ts:182-245`) supports three forms —
directory, flat file, legacy `system.*` — and when both a flat file and a directory exist,
**both are used, flat file first** (`:189-190`, `:225-227`). Legacy `system.*` emits a
deprecation diagnostic (`:255-262`). Missing entirely ⇒ a required-slot diagnostic
listing every legal filename (`:283-290`).

#### Eve's ordering rule

```ts
// vercel-eve/packages/eve/src/discover/grammar.ts:170-179
entries.sort((left, right) => left.name.localeCompare(right.name));
```

Depth-first, subdirectories before leaves, alphabetical within a level
(`src/discover/named-source-directory.ts:97-108`, `:204-224`).
**`localeCompare` is locale-dependent** — see §5.1.

#### Case sensitivity asymmetry

Eve matches slot **files** case-insensitively (`filesystem.ts:136`, `:144`, `:220`, `:228`,
`:292`; `src/discover/slots.ts:42`; test at `src/discover/agent.integration.test.ts:234`)
but slot **directories** case-sensitively (`filesystem.ts:154-203`, all `name === "…"`).
So `Instructions.md` works and `Instructions/` does not.

#### What Eve does *not* have (verified by absence in the slot table)

No inheritance/`extends`, no variants, no model abstraction, no eval slot at the agent
root (evals live under `src/evals/`), no topology slot beyond `subagents/`, no versioning
of the definition. Escape hatch is TypeScript modules only
(`SUPPORTED_AUTHORED_MODULE_FILE_EXTENSIONS`, `filesystem.ts:7-14`) — which is exactly the
"TS-only escape hatch" the thesis calls out, now with a citation.

---

### 2.8 Continue — `filedef/continue`

Continue has the corpus's most developed **package composition** model.

| Aspect | Finding | Evidence |
|---|---|---|
| Config form | `config.yaml` (assistant) + markdown blocks | `packages/config-yaml/src/load/unroll.ts:32-83` |
| Composition | `uses: <package-id>` + `with: {…}` template inputs; recursively "unrolled" | `unroll.ts:412-462`, `:498-520` |
| Templating | `${{ inputs.X }}` / `${{ secrets.Y }}`; unresolved vars are **left as the literal expression** rather than erroring | `unroll.ts:99-116` |
| Secrets | Fully-qualified secret names (`parentSlug/…/secret`) so a nested block's secret is namespaced by its import path | `unroll.ts:143-168` |
| Merge (packages) | **Array concatenation** for `models, context, data, mcpServers, rules, prompts, docs`; object spread for `env` | `load/merge.ts:5-24` |
| Merge (assistants) | Concatenate `incoming` then `current`, then **dedupe by name** — `incoming` wins | `load/merge.ts:39-56` |
| Dedup key | `rules`: the string itself, or `.name`; `context`: `name ?? params.title ?? provider`; everything else: `.name` | `load/blockDuplicationDetector.ts:13-27` |
| Override | `mergeOverrides` — shallow, key-wise, last wins | `unroll.ts:832-838` |
| Rule frontmatter | `globs, regex, name, description, alwaysApply, invokable` | `markdown/markdownToRule.ts:8-16` |
| Rule "type" | **Derived**, not declared: globs/regex ⇒ AutoAttached; description + `alwaysApply:false` ⇒ AgentRequested; `alwaysApply:false` alone ⇒ Manual; else Always | `markdown/getRuleType.ts:24-53` |
| Glob rebasing | A colocated rule's globs are **rewritten** relative to its directory (`**/`-prefixed) — unless the path contains `.continue` | `markdownToRule.ts:71-93` |
| Name fallback | Last **two** path segments joined by `/` | `markdownToRule.ts:51-69` |
| Agent files | Experimental `AgentFile`: frontmatter `name` (required), `description, model, tools, rules` (all **strings**, with `// TODO also accept yaml array`) + markdown body ⇒ `prompt` | `markdown/agentFiles.ts:8-20`, `:46-68` |
| Discovery | `.continue/<subdir>` per workspace root + `~/.continue/<subdir>`; recursive `walkDir` with an ignore-file override; per-file failures collected as **non-fatal** `ConfigValidationError`s | `core/config/loadLocalAssistants.ts:101-124`, `:50-93`; `core/config/markdown/loadMarkdownSkills.ts:94-105` |

**Frontmatter split bug (verified by reading):**

```ts
// continue/packages/config-yaml/src/markdown/markdownToRule.ts:28-31
const parts = normalizedContent.split(/^---\s*$/m);
if (parts.length >= 3) { …treat parts[1] as YAML frontmatter… }
```

The `m` flag means the delimiter matches at **any** line start, not just the document
start. A markdown file with **two horizontal rules and no frontmatter** yields
`parts.length === 3` and the prose between them is fed to `YAML.parse`. If that prose
parses as a YAML scalar, `frontmatter` becomes a string, all field accesses are `undefined`,
and `markdown` silently becomes only the text after the second `---`. Silent content loss,
no diagnostic (`:33-43`).

**Design lesson:** Continue's `alwaysApply`/`globs`/`description` → *derived* rule type
(`getRuleType.ts:24-53`) is a nice no-code ergonomic (D13/D14) but it means the same
document means different things depending on which optional fields are present. PACT
should prefer an explicit discriminator with a *defaulting* rule over an inferred one,
so error messages can name the rule violated (`O7.3`).

---

### 2.9 Cline — `filedef/cline`

Covered in §2.5. Additional:

| Aspect | Finding | Evidence |
|---|---|---|
| State in the file | Enable/disable is stored as `disabled: true` **in SKILL.md frontmatter**, because the SDK reads enablement from the file, not the UI | `apps/vscode/…/user-instructions/skills.ts:12-26`, `:28-56` |
| Round-trip serialisation | `yaml.dump(data, {schema: yaml.JSON_SCHEMA})` then `---\n…\n---\n<body>` — **frontmatter key order and comments are not preserved** | `skills.ts:58-61` |
| Remote skills | Enterprise-pushed skills with `remote:` pseudo-paths; identity is frontmatter `name`, drift from the dashboard name is **warned, not rejected** ("would silently hide org-configured skills") | `skills.ts:105-126` |

**Relevant to D18** ("a UI that reads/writes the same files"): cline demonstrates the
UI-writes-file pattern *and* its cost — a rewrite loses comments and key order. PACT's
`AC-1.4`/`O7` will need either a comment-preserving YAML writer or an explicit statement
that machine writes are lossy for trivia.

---

### 2.10 Roo Code — `filedef/roo-code`

Roo Code is the only system in the corpus that implements a **directory → string field**
expansion for instructions, i.e. the closest live analogue of PACT's Expansion Rule for a
scalar field.

| Aspect | Finding | Evidence |
|---|---|---|
| Mode schema | `slug` (`^[a-zA-Z0-9-]+$`), `name`, `roleDefinition`, `whenToUse?`, `description?`, `customInstructions?`, `groups`, `source?` | `packages/types/src/mode.ts:91-102` |
| Duplicate detection | Duplicate mode `slug`s rejected; duplicate tool `groups` rejected | `mode.ts:107-129`, `:60-79` |
| Deprecation | Deprecated tool groups are **stripped by a preprocess step** before validation, for backward compat | `mode.ts:81-89` |
| Schema publishing | Zod → JSON Schema draft-07 with `$id`, generated *and* drift-tested | `packages/types/src/roomodes-schema.ts:36-58` |
| Strictness | `.roomodes` top level is `.strict()` | `roomodes-schema.ts:37-41` |
| **Rules directory** | `.roo/rules/` (global then project) → each file read, concatenated | `src/core/prompts/sections/custom-instructions.ts:206-239` |
| Mode-scoped rules | `.roo/rules-<mode>/` — **the field name is encoded in the directory name** | `custom-instructions.ts:409-419` |
| Provenance | Each file contributes `# Rules from <relpath>:\n<content>` | `custom-instructions.ts:187-197` |
| **Directory beats file** | If any `.roo/rules*/` directory yields ≥1 file, legacy `.roorules` / `.clinerules` are **not read at all** | `custom-instructions.ts:223-238`, `:421-438` |
| Ordering | Recursive readdir, then sort by `path.basename(sortKey).toLowerCase()` with `localeCompare` | `custom-instructions.ts:168-176` |
| Junk filter | Hardcoded **denylist** of 20 patterns (`*.DS_Store`, `*.swp`, `*.tmp`, `*.bak`, `Thumbs.db`, …) | `custom-instructions.ts:513-548` |
| Symlinks | Followed, including symlinked directories; **cycle protection is a depth cap `MAX_DEPTH = 5`**, not a visited-set | `custom-instructions.ts:46`, `:51-117` |
| AGENTS.md | `AGENTS.md` → fallback `AGENT.md` (first hit wins), **plus** `AGENTS.local.md` always appended | `custom-instructions.ts:288-331` |
| AGENTS.md scope | Root only by default; `enableSubfolderRules` ⇒ **all** subdirectory AGENTS.md concatenated | `custom-instructions.ts:355-378` |

**Two verified defects in the ordering rule** (`custom-instructions.ts:168-176`):

1. The walk is `recursive: true` (`:124-127`) but the sort key is `path.basename(...)` only.
   `a/z.md` and `b/a.md` sort as `z.md` vs `a.md`; two files with the *same* basename in
   different subdirectories have **no defined relative order** (`Array.prototype.sort` is
   stable in modern V8, so they fall back to readdir order — which is not specified).
2. `localeCompare` without an explicit locale uses the host's default ICU collation:
   ordering of `_`, `-`, digits, and accented characters varies by locale. Combined with
   `.toLowerCase()`, `A.md` and `a.md` tie.

**Symlink cycle:** a symlink loop of length < 5 is traversed repeatedly and its contents
duplicated in the output until the depth cap fires; it never errors. goose's canonicalised
visited-set (`goose/…/skills/mod.rs:379-385`) is the correct pattern.

---

### 2.11 Opencode — `filedef/opencode`

| Aspect | Finding | Evidence |
|---|---|---|
| Config discovery | Walk **up** from cwd to worktree root collecting `opencode.jsonc`/`opencode.json`, then `.toReversed()` so root-most merges first (nearest wins) | `packages/opencode/src/config/paths.ts:11-21` |
| Directory chain | `~/.config` global, `.opencode` dirs walking up, `$OPENCODE_CONFIG_DIR`, deduped | `config/paths.ts:23-42` |
| Agents | Glob `{agent,agents}/**/*.md` per config dir, `dot: true`, `symlink: true` | `config/agent.ts:13-18` |
| Name derivation | `configEntryNameFromPath(path.relative(dir, item), ["agent/","agents/"])`; nested dirs become part of the name; extension stripped | `config/entry-name.ts:8-19` |
| **Real-world bug** | Comment records issue **#25713**: matching the prefix anywhere in an **absolute** path mis-keyed agents whose home/parent segments happened to contain `agent/`. Fixed by anchoring to a relative path | `config/entry-name.ts:4-7` |
| Collision | `result[config.name] = …` — **last glob hit silently wins**, no duplicate diagnostic | `config/agent.ts:29` |
| Frontmatter | Strict YAML parse; failure raises `FrontmatterError` naming the path; a *separate* permissive `sanitize` path exists because "other coding agents like claude code allow invalid yaml in their frontmatter" | `config/markdown.ts:21-23`, `:25-38` |
| Unknown keys | **Rejected at top level** with `unrecognized_keys` and the key list; nested/index-signature schemas exempt | `config/parse.ts:34-55`, `:67-73` |
| Agent schema | `model, variant, temperature, top_p, prompt, tools(dep), disable, description, mode(subagent\|primary\|all), hidden, options, color, steps, maxSteps(dep), permission` + open rest record | `packages/core/src/v1/config/agent.ts:13-41` |
| Migration | `normalize()` folds unknown keys into `options`, maps legacy `tools:{write:true}` → `permission.edit: allow`, `maxSteps` → `steps` — as a **decode transform**, so it runs on every load | `core/src/v1/config/agent.ts:43-84` |
| Merge | `remeda.mergeDeep`; arrays **replaced**, except `instructions`, which is concatenated + `Set`-deduped as a special case in code | `config/config.ts:40-51`, `:459-461` |
| Skill registry | Remote `index.json` → `{skills:[{name, files[], version?}]}`; entries lacking `SKILL.md` warned and skipped; version change triggers download-to-staging + atomic rename with rollback | `src/skill/discovery.ts:13-21`, `:66-73`, `:88-124` |

**Two transplantable ideas:** (1) the *decode-time normalize* pattern for deprecated fields
(`core/src/v1/config/agent.ts:62-79`) is exactly how PACT should implement
`bud.dev/v1 → pact.dev/v1` (D3) without a separate migration tool pass; (2) the
staging-directory + atomic-rename + rollback install (`skill/discovery.ts:96-124`) is the
right shape for PACT's registry seam under D24.

**One anti-pattern:** hardcoding `instructions` as the one concatenating array
(`config/config.ts:45-51`). **Merge strategy must be a schema annotation, not an `if`.**

---

### 2.12 Aider — `filedef/aider`

Minimal, and instructive because of that.

| Aspect | Finding | Evidence |
|---|---|---|
| Config file | `.aider.conf.yml` | `aider/main.py:464` |
| Search order | cwd → git root → `~`, then **`.reverse()`** so home is applied first and cwd last (nearest wins) | `aider/main.py:466-497` |
| Discoverability | `--verbose` prints the search order with `(exists)` markers | `aider/main.py:492-496` |
| Composition | None — flat key/value config consumed by ConfigArgParse; conventions are conveyed by adding a plain `CONVENTIONS.md` to the chat as context | `aider/args.py:788-799` |
| Versioning | None | — |

**Lesson for `O7.3`:** printing the resolved search order with existence markers is a
cheap, high-value diagnostic. PACT's `pact explain` should do exactly this for every field.

---

### 2.13 AGENTS.md — `protocols/agents-md`

- **No specification.** The repository is a Next.js marketing site; the only normative-ish
  content is prose in a React component.
- **Nesting rule as published:** "Place another AGENTS.md inside each package. Agents
  automatically read the **nearest** file in the directory tree, so the **closest one takes
  precedence**" (`components/HowToUseSection.tsx:34-39`).
- **Implementations disagree with the published rule.** roo-code concatenates *all* of
  them when subfolder rules are enabled (`roo-code/src/core/prompts/sections/custom-instructions.ts:355-378`),
  and additionally appends an unversioned `AGENTS.local.md` per directory
  (`:325-331`). "Nearest wins" and "concatenate all" are not the same function.
- No frontmatter, no schema, no version, no identity. Purely a context-injection convention.

**Consequence for PACT:** `AGENTS.md` cannot be a PACT input with defined semantics; it can
only be an *importable hint*. If PACT reads it, the loader must state which rule it uses
and emit it in the provenance record.

---

### 2.14 Dify — `frameworks2/dify` (YAML DSL)

| Aspect | Finding | Evidence |
|---|---|---|
| Form | **Single flat YAML document**, exported from the database | `api/services/app_dsl_service.py:604-660` |
| Envelope | `version`, `kind: app`, `app: {name, mode, icon, …}`, then `workflow:` / `agent:`+`agent_packages:` / `model_config:`, plus `dependencies: []` | `app_dsl_service.py:622-659` |
| Current version | `CURRENT_APP_DSL_VERSION = "0.7.0"` | `api/constants/dsl_version.py:1` |
| **Version policy** | Tri-state: imported > current ⇒ `PENDING` (needs confirmation); imported.major < current.major ⇒ `PENDING`; imported.minor < current.minor ⇒ `COMPLETED_WITH_WARNINGS`; else `COMPLETED`; unparseable ⇒ `FAILED` | `api/services/dsl_version.py:5-19` |
| Missing version | Silently defaulted to `"0.1.0"`; missing/incorrect `kind` silently forced to `"app"` | `app_dsl_service.py:192-196` |
| Composition | `dependencies` list of plugin/package refs, resolved against a marketplace | `app_dsl_service.py:650-659` |
| Directory form | **None.** | — |

**The version policy is the best in the corpus** and is directly usable: PACT's
`ImportReport`/`ExportReport` should carry the same graded outcome
(`ok | warnings | needs-confirmation | failed`) rather than a boolean. The silent
defaulting at `:192-196` is the anti-pattern to avoid under `AC-7.1`.

### 2.15 Langflow — `frameworks2/langflow`

| Aspect | Finding | Evidence |
|---|---|---|
| Form | One `.json` per flow — a serialisation of the canvas graph | `src/backend/base/langflow/initial_setup/setup.py:1046-1052` |
| Discovery | `Path(flows_path).iterdir()`, **non-recursive**, `.json` only | `setup.py:1046-1048` |
| Identity | UUID *inside* the file; fallback match by `endpoint_name`, then `(user_id, name)` | `setup.py:1317-1335` |
| Collision policy | Name-matched but id-differs ⇒ **skip with a warning** unless `LANGFLOW_LOAD_FLOWS_OVERWRITE_ON_NAME_MATCH=true` | `setup.py:1274-1281` |
| Truth | The database; files are an import channel | `setup.py:1022-1052` |
| Versioning | None in the file | — |

Confirms thesis §1.3: framework-native low-code formats are runtime object-graph dumps,
not authoring surfaces. Note the one good idea: **an explicit, named flag governing
identity-collision override**, rather than implicit last-wins.

---

### 2.16 Next.js App Router — `filedef/nextjs-app-router` **[NEW IN v2]**

The directory `research/repos/filedef/nextjs-app-router` is **the Next.js monorepo**, not a
sample application. v1 skipped it. It should not have: the App Router is the most widely
deployed "a directory tree is a structured document" system in existence, it has been
through the exact evolutionary pressures PACT is about to face, and unlike every agent tool
in the corpus it has **a build-time validator whose job is to refuse ambiguity**.

#### 2.16.1 The slot table — same shape as Eve's, bigger, and also hardcoded

```ts
// nextjs-app-router/packages/next/src/build/webpack/loaders/next-app-loader/index.ts:81-89
const FILE_TYPES = {
  layout: 'layout',
  template: 'template',
  error: 'error',
  loading: 'loading',
  'global-error': 'global-error',
  'global-not-found': 'global-not-found',
  ...HTTP_ACCESS_FALLBACKS,          // not-found | forbidden | unauthorized
} as const
```

plus `page`, `route` and `default`, matched by regex factories rather than by the table
(`packages/next/src/server/lib/find-page-file.ts:90-105`). Twelve slots, hand-maintained,
and `FILE_TYPES` is **mutated at module scope behind a feature flag**
(`next-app-loader/index.ts:695-698`, `delete FILE_TYPES['global-not-found']`). This is Eve's
problem at ten thousand times the scale, and it confirms that the closed-slot-table design
does not stop growing — it just accumulates conditionals.

#### 2.16.2 The part PACT does not have: three directory sigils

This is the finding. Next.js needed, and shipped, exactly three one-character rules that
change what a directory *is*, all of them declared in-band by the directory's own name:

| Sigil | Meaning | Evidence |
|---|---|---|
| `(group)` | The directory contributes **nothing** to identity. Pure organisation. | `packages/next/src/shared/lib/segment.ts:7-10` (`isGroupSegment`); consumed at `shared/lib/router/utils/app-paths.ts:31-34` ("Groups are ignored") |
| `@slot` | The directory **is a named field** of its parent, not a path segment. The parent renders `{children, modal, sidebar}` as separate fields. | `segment.ts:12-14` (`isParallelRouteSegment`); `app-paths.ts:36-39` ("Parallel segments are ignored"); field extraction at `build/file-classifier.ts:13-25` |
| `_private` | The directory takes **no part in discovery**. | `build/route-discovery.ts:99` — `ignorePartFilter: (part) => part.startsWith('_')` |

`@slot` is literally the Expansion Rule: *this directory is a field named `slot`*, sitting
alongside path-segment directories in the same tree, distinguished by one character.
Next.js needed a sigil precisely because a directory name is otherwise overloaded — it is
simultaneously identity, organisation, and structure, and no amount of type declaration
disambiguates them at authoring time.

**Why this matters to PACT.** PACT's `agents/` is a map from name → agent, and an author
who groups agents (`agents/finance/refund-desk/agent.yaml`) is refused: the CLI answers
`loader/nothing-can-run-this` and tells them to move it
(`crates/pact-cli/tests/the_workspace_a_check_finds_is_the_workspace_a_runtime_finds.rs:419-451`).
That is *correct* under the Expansion Rule — `agents` is typed `map<name, Agent>`, not a
nested map — but it means **PACT has no way to organise without renaming**, and the agent
name is the published identity (`pact:<name>`, §5A.10). Next.js hit exactly this in the
Pages Router and answered it with `(group)`. PACT has not reserved the character.

#### 2.16.3 Ambiguity is a build-time error, and the error enumerates every offender

`validateAppPaths` (`packages/next/src/build/validate-app-paths.ts:202-281`) is the closest
thing in the entire corpus to what PACT's loader needs to be. It:

- validates each path individually, then cross-validates (`:206-252`);
- normalises dynamic segments to a wildcard so structurally-identical routes collide
  (`normalizeSegments`, `:168-186`);
- collects **all** conflicts and throws one error listing every path
  (`:255-278`) — not first-wins, not last-wins, not a warning.

Two of its individual rules are directly transplantable:

```ts
// validate-app-paths.ts:104-114 — punctuation-insensitive identity collision
const normalizedSegment = segment.param.paramName.replace(/\W/g, '')
if (normalizedSegments.has(normalizedSegment)) {
  throw new Error(
    `You cannot have the slug names "${existing}" and "${segment.param.paramName}" differ
     only by non-word symbols within a single dynamic path in route "${route.pathname}".`)
}
```

This is the *generalisation* of PACT's `fold_key` NFC-and-case rule: Next.js refuses two
identifiers that differ **only by punctuation**, on the grounds that a human reader cannot
tell them apart. PACT folds case and normalisation but not punctuation, so `refund-desk`
and `refund_desk` (or `refunddesk`) are distinct agents in one workspace. Given that PACT
identifiers reach an A2A card and a registry, and that `_` and `-` are the two separators
authors mix freely, this is worth adopting.

#### 2.16.4 The ordering natural experiment

Next.js sorts in two places, with two different comparators, and only one has a bug.

```ts
// packages/next/src/lib/recursive-readdir.ts:177-180 — discovery
// Sort the pathnames in place if requested.
if (sortPathnames) { pathnames.sort() }        // UTF-16 code-unit order. Locale-free.
```
```ts
// packages/next/src/shared/lib/router/utils/app-paths.ts:58-70 — manifest ordering
 * Without this, route group prefixes like `(group)` (char code 0x28) sort
 * before `@` (0x40), causing the children page to sort first instead of last
 * and leading to a manifest mismatch / 404 in webpack dev mode.
export function compareAppPaths(a: string, b: string): number {
  const aHasSlot = a.includes('/@'); const bHasSlot = b.includes('/@')
  if (aHasSlot && !bHasSlot) return -1
  if (!aHasSlot && bHasSlot) return 1
  return a.localeCompare(b)
}
```

The docstring is a post-mortem: a **shipped 404** caused by sort order between two sigil
characters, patched by hoisting the sigil out of the comparator rather than by fixing the
comparator. `localeCompare` remains as the tie-break. This is the best available evidence
for v1's §5.1 rule, and it also warns about something v1 did not: **a sigil alphabet whose
characters are compared by their code points creates ordering coupling between sigils.**
PACT's ordinal prefix (`NN-`) already has this shape — an ordinaled entry sorts before a
non-ordinaled one by an explicit branch (`crates/pact-loader/src/lib.rs:915-921`), which is
the right pattern (explicit tier, then key), and should be preserved if sigils are added.

#### 2.16.5 Case-insensitive filesystems, solved in production

```ts
// packages/next/src/server/lib/find-page-file.ts:12-21
async function isTrueCasePagePath(pagePath: string, pagesDir: string) {
  const pageSegments = normalize(pagePath).split(sep).filter(Boolean)
  const segmentExistsPromises = pageSegments.map(async (segment, i) => {
    const segmentParentDir = join(pagesDir, ...pageSegments.slice(0, i))
    const parentDirEntries = await fsPromises.readdir(segmentParentDir)
    return parentDirEntries.includes(segment)          // exact string membership
  })
  return (await Promise.all(segmentExistsPromises)).every(Boolean)
}
```

On macOS/Windows, `fileExists("Foo.tsx")` returns true when the file on disk is `foo.tsx`.
Next.js defends by **re-enumerating the parent and doing exact membership**, per path
segment, and returning `null` if the case does not match (`find-page-file.ts:38-40`).

**This validates a PACT design choice that was not previously named as one.** PACT's loader
*enumerates* (`read_dir` → classify → fold) rather than *probing* a constructed path, so it
is structurally immune to this bug class. Every system in the corpus that probes needs a
true-case check and only Next.js has one: goose probes `<name>.yaml` then `<name>.json`
(`recipe/local_recipes.rs:106-119`), prompty probes `${file:…}`
(`prompty/spec/spec.md:510-524`), Eve probes slot names case-insensitively
(`filesystem.ts:136,144`). **The rule to write down: PACT resolves fields by enumerating a
directory and folding names, never by opening a constructed filename.** Anywhere PACT does
probe — `evals: /evals/suite.yaml`, `loop: careful`, `policy: approvals`, `.pactignore` —
the same true-case obligation applies.

#### 2.16.6 What Next.js does *worse*, and PACT should not copy

- **Duplicate encodings of one slot are a warning, and the winner is config order.**
  `getPagePaths` enumerates `page.js, page.jsx, page.ts, page.tsx` in `pageExtensions` order
  (`shared/lib/page-path/get-page-paths.ts:32-37`); `findPageFile` takes
  `[existingPath, ...others]` and merely `warn()`s when `others.length > 0`
  (`find-page-file.ts:39-48`). So `page.ts` + `page.tsx` silently resolves to whichever the
  user's config listed first. PACT errors on the equivalent (`instructions.md` +
  `instructions.yaml` → `loader/duplicate-field`, §5A.1) — **PACT is right and should stay
  right.**
- **Symlinks are followed** (`recursive-readdir.ts:143-175` stats each link and pushes the
  target into the walk) with no containment check and no cycle set. PACT refuses them
  outright, which is stricter and correct for a supply-chain surface — *except* in the
  self-file branch (§0.2 item 8).

---

## 3. Cross-cutting comparison

### 3.1 Frontmatter: eleven parsers, eleven behaviours

| System | Delimiter rule | Anchored to doc start? | Malformed YAML | Unknown keys |
|---|---|---|---|---|
| prompty | `---` or `+++`, either may close the other | Yes (`^\s*`) | **MUST error** | Preserved / ignored, MUST NOT error |
| dotprompt | `---` only, allows leading `#` header lines | Yes | **Fail-open**: whole file becomes template | Dotted ⇒ `ext`; undotted ⇒ dropped from typed view |
| goose | `content.split("---")`, `len>=3` | **No** | Error propagated as `serde_yaml::Error` | Nested `metadata:` bag / `#[serde(flatten)]` |
| cline | `/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/`, BOM stripped | Yes | Fail-open **but reports `parseError`** | Kept in `data` record |
| continue | `split(/^---\s*$/m)`, `parts>=3` | **No** | Fail-open, `console.warn` | Ignored by typed interface |
| opencode | delegated, strict | Yes | **`FrontmatterError` with path** | **Rejected** at top level |
| Eve | markdown lowerers per slot | — | Diagnostic | Diagnostic |

*Evidence:* `prompty/spec/spec.md:180-223`; `dotprompt/js/src/parse.ts:67-68`, `:230-233`;
`goose/crates/goose/src/sources.rs:20-32`; `cline/…/frontmatter.ts:42-58`;
`continue/…/markdownToRule.ts:28-43`; `opencode/…/config/markdown.ts:25-38`,
`config/parse.ts:34-55`.

**Six of seven differ on at least one of: anchoring, failure mode, unknown-key policy.**

### 3.2 Identity: path vs frontmatter

| Rule | Systems | Evidence |
|---|---|---|
| Frontmatter wins; path is fallback | goose skills, continue rules | `goose/…/skills/mod.rs:235-248`; `continue/…/markdownToRule.ts:51-69` |
| Frontmatter **must equal** path | cline skills | `cline/…/skills.ts:193-196` |
| Path wins entirely | opencode agents, dotprompt, genkit, Eve | `opencode/…/config/agent.ts:22`; `dotprompt/js/src/stores/dir.ts:250-256` |
| Embedded UUID wins, path irrelevant | langflow | `langflow/…/setup.py:1317-1335` |

### 3.3 Precedence and merge

| System | Roots | Winner | Merge of same-kind collections |
|---|---|---|---|
| goose skills | 7+ roots, project→global | **first** | n/a (dedup by name) |
| goose recipes | 6 roots, sorted+deduped | **first** | n/a |
| cline skills | 6 roots | **last** (remote>global>project) | n/a |
| continue | `.continue` + `~/.continue` | incoming wins after dedupe | **concatenate** all block arrays |
| opencode | up-walk, root-first | **last** (nearest) | deep-merge objects; arrays replaced **except `instructions`** |
| aider | cwd→git→home, reversed | **last** (nearest) | n/a |
| roo-code rules | global then project | **concatenate both** | string concatenation with provenance headers |
| Eve | single agent root | n/a | flat file + directory **both**, file first |

*Evidence:* §2.5–§2.12 tables above.

**There is no majority.** first-wins, last-wins, and concatenate-all are each used by
multiple systems, sometimes within one product for different field kinds.

### 3.4 Versioning story

| System | Definition version | Content version | Compatibility policy |
|---|---|---|---|
| prompty | none (convention in `metadata`) | none | none |
| dotprompt | `version` reserved key + **sha1(content)[0:8]** | yes | mismatch ⇒ error on load |
| promptl | none | **sha256(text ‖ referenced hashes)** | none |
| goose recipe | `version` semver string, default `1.0.0` | none | not enforced in loader read |
| opencode skills | `version` in remote index | none | version change ⇒ atomic re-download |
| roo-code | JSON Schema `$id` + drift test | none | deprecated enum members preprocessed away |
| dify | `version` semver + `kind` | none | **graded 4-state policy** |
| Eve / cline / continue / aider / langflow | none | none | none |

**Only two systems (dotprompt, promptl) content-address, and only promptl's hash is
transitive.** PACT needs both: `pact.lock` must pin a *transitive* digest.

---

## 4. "Is a directory a field?" — precedent analysis

### 4.1 The formal precedent: CUE

This is the answer. CUE already defines exactly this construct, and its soundness argument
is explicit:

- **A directory of files is one value.** "All source files within a module with the same
  package name belong to the same package… An *instance* of a package is any subset of
  files belonging to the same package… It is interpreted as the concatenation of these
  files." — `config/cue/doc/ref/spec.md:3164-3175`.
- **The merge operator is order-independent.** "Unification in CUE is a binary expression,
  written `a & b`. It is **commutative, associative, and idempotent**. As a consequence,
  **order of evaluation is irrelevant**, a property that is key to many of the constructs
  in the CUE language as well as the tooling layered on top of it."
  — `config/cue/doc/ref/spec.md:670-674`.
- **Because values form a lattice, the merge is unique**: "All possible values are ordered
  in a lattice, a partial order where every two elements have a single greatest lower
  bound." — `:597-598`; unification is that greatest lower bound (`:655-663`).
- **Conflicts are errors, not overrides**: "The unification of a value with bottom is
  always bottom" (`:669`) — i.e. incompatible concrete values annihilate to an error.

**This gives the defensible general rule.** "A directory is a field" is sound *precisely
when* the operation that turns N children into one value is a commutative, associative,
idempotent, conflict-detecting merge — a lattice meet. It is **not** sound when the
operation is last-wins override or ordered concatenation, because both make the value a
function of an ordering the filesystem does not canonically provide.

**And CUE tells us where it breaks:** lists are ordered (`spec.md:1780-1799` models a list
as a linked struct with `Elem`/`Tail`), so unifying lists of different shape fails. Ordered
constructs are *not* expressible as unordered directory merges.

### 4.2 The engineering precedent: Kustomize chose explicit enumeration

The Kustomize overlays present in the corpus never rely on directory scanning:

```yaml
# eval/phoenix/kustomize/base/kustomization.yaml:1-3
resources:
  - phoenix.yaml
  - postgres.yaml
```
```yaml
# eval/phoenix/kustomize/auth/kustomization.yaml:1-4
bases:
  - ../../base
patchesStrategicMerge:
  - patches.yaml
```

Two properties worth copying: (1) **membership and order are declared in-band**, so adding
a stray file to the directory cannot change the output; (2) **the merge strategy is named
at the point of use** (`patchesStrategicMerge`), not implied by location.

Same pattern in `config/kubevela/config/crd/kustomization.yaml`,
`config/crossplane/cluster/composition/kustomization.yaml`,
`frameworks2/llamaindex-workflows/examples/k8s-otel/k8s/kustomization.yaml`.

### 4.3 Helm: directory conventions + values, but text templating

A real chart in the corpus (`routing/litellm/helm/litellm-helm/`) shows the layout:
`Chart.yaml`, `values.yaml`, `templates/` (15 files incl. `_helpers.tpl`, `NOTES.txt`),
`charts/`, `Chart.lock`, `ci/`, `tests/`. `Chart.yaml` declares `apiVersion: v2`, `name`,
`type: application`, and a semver `version` whose contract is spelled out in comments
(`Chart.yaml:1-20`).

The transplantable parts: a **lockfile for dependencies** (`Chart.lock`), a **`_`-prefix
convention for non-emitting partials** (`templates/_helpers.tpl`, same convention as
dotprompt's `_partial.prompt`), and **CI fixtures colocated with the chart** (`ci/`).
The non-transplantable part is text-templating the YAML, whose failure mode goose
independently rediscovered (§2.6.1).

### 4.4 Pkl: how inheritance over *ordered* collections actually works

Pkl's `amends` is the corpus's cleanest inheritance model, and its treatment of ordered
collections is the key datum:

```pkl
// config/pkl/docs/modules/language-reference/pages/index.adoc:1391-1404
birds2 = (birds) {
  new { name = "Barn owl"; diet = "Mice" }   // append
  [0] { diet = "Worms" }                      // amend element 0 in place
  [1] = new { name = "Albatross"; … }         // replace element 1
}
```

Three distinct operations — append, amend-at-index, replace-at-index — each requiring an
**explicit positional address**. There is no way to say "merge these two lists" without
saying where. Any PACT directory form for an ordered field must therefore carry position
in-band (numeric prefix, explicit `order:`, or an index file).

### 4.5 OCI: what "canonical" has to mean

`protocols/oci-image-spec/considerations.md:17-36`:

- Content-addressability requires canonical serialisation, else "the same semantic layer
  would have a different hash" and stores duplicate (`:19-25`).
- All `+json` content **MUST** follow I-JSON (RFC 7493): UTF-8 encoding; numbers SHOULD be
  IEEE-754 double; **objects MUST NOT contain duplicate names** (`:29-33`).
- "The order of entries in JSON objects is not significant. Implementations MAY implement
  Canonical JSON documented in RFC 8785." (`:35-36`)

These are the exact rules `canonical.json` needs to satisfy `O1.2` and `AC-1.4`.

### 4.6a Kubernetes: merge strategy **is** a schema annotation **[NEW IN v2]**

v1's §5.6 recommended that PACT annotate merge strategy in the schema
(`x-pact-merge: …`) and noted that "only Kustomize makes strategy data". That understated
the precedent. Kubernetes carries the merge contract **on the field, in the type
definition**, and it has been doing so since strategic-merge-patch:

```
// config/kubevela/e2e/addon/mock/testdata/fluxcd/resources/crds/bucket.yaml:141-144
//   +patchMergeKey=type
//   +patchStrategy=merge
//   +listType=map
//   +listMapKey=type
//   Conditions []metav1.Condition `json:"conditions,omitempty"
//     patchStrategy:"merge" patchMergeKey:"type" ...`
```

Four orthogonal annotations, three of which PACT needs:

| Annotation | Question it answers | PACT analogue |
|---|---|---|
| `listType` ∈ `atomic \| set \| map` | Is this list replaced wholesale, a set, or keyed? | the fold `⊕_T` |
| `listMapKey` | **Which field identifies an element** | the directory-entry name |
| `patchStrategy` ∈ `merge \| replace \| retainKeys` | How does an overlay combine? | variant/profile overlay semantics |
| `patchMergeKey` | Identity under patching | same as `listMapKey` |

Two consequences for T5 that v1 missed:

1. **`listType: map` + `listMapKey` is the general escape from the ordered-field problem.**
   v1 concluded (§6.3.2) that ordered fields "do not get a free directory form" and must
   carry order in-band via `NN-` prefixes. Kubernetes shows the third option: *a list whose
   elements have a declared identity key is not really ordered* — it is a map, and a map has
   a directory form for free, with no ordinal and no tie-breaking. PACT should classify each
   collection field as `set | map(key) | sequence` in the schema, and only `sequence`
   requires the ordinal prefix. That shrinks the ordinal's blast radius, which is exactly
   what §0.2 item 7 says is currently too large.
2. **Naming the strategy on the field kills the special case.** KubeVela's CUE templates use
   the same idea inside a config language (`+patchKey=name`,
   `config/kubevela/charts/vela-core/templates/defwithtemplate/command.yaml:83`,
   `configmap.yaml:21`), which is the counter-example to opencode hardcoding `instructions`
   as its one concatenating array (`opencode/…/config/config.ts:45-51`).

### 4.6 Systems not verifiable offline

Nix, Hugo content trees, and Jekyll collections are not in the local corpus and I did not
use the network. I therefore make **no** claims about them. The one structural point I can
make from artefacts present: Jekyll/Hugo-style "front matter + content tree" is the same
shape as every `SKILL.md`/`*.prompt` system surveyed here, and inherits the identical
ordering/collision problems documented in §5.

---

## 5. Failure modes of "a directory is a field" — with evidence

### 5.1 Ordering — **the primary hazard, and it is already biting**

| Evidence | Problem |
|---|---|
| `vercel-eve/…/discover/grammar.ts:176` | `left.name.localeCompare(right.name)` — **locale-dependent collation** |
| `roo-code/…/custom-instructions.ts:171-175` | `localeCompare` on `basename(...).toLowerCase()` — locale-dependent **and** loses the directory component in a recursive walk **and** ties on case-differing names |
| `goose/…/skills/mod.rs:388-402` | raw `read_dir` order, unsorted; combined with first-wins dedup at `:433-451` this makes the *winner* depend on filesystem inode order |
| `genkit/js/ai/src/prompt.ts:785-788` | raw `readdirSync` order |
| `opencode/…/config/agent.ts:13-29` | glob order + `result[name] = …` last-wins |

**Nobody in the corpus specifies a byte-deterministic order.** Two of the five use
`localeCompare`, which by definition varies with the host's ICU locale.

**Rule PACT must adopt:** order by the **UTF-8 byte sequence** of the path component
(equivalently: code-unit order after NFC normalisation), never `localeCompare`, never
case-folded, and always over the **full relative path**, not the basename.

### 5.2 Duplicate keys — **[EMPIRICAL]**

```
$ printf 'name: a\nname: b\n' > dup.yaml
$ python3 -c "import yaml; print(yaml.safe_load(open('dup.yaml')))"
{'name': 'b'}          # silent last-wins, no warning
```

Rust's `serde_yaml` is stricter: deserialising into `Value`/`Mapping` returns
`DuplicateKeyError` (`serde_yaml-0.9.34+deprecated/src/mapping.rs:807-831`), and serde's
derived struct deserialiser errors with `duplicate field`. So **the Rust core (D4) rejects
what a Python provider (D4/D6) silently accepts**.

At the *directory* level the analogue is two files claiming the same field. Only
roo-code (`mode.ts:107-129`) and continue (`blockDuplicationDetector.ts:29-36`) detect
duplicates at all, and both do it by *silently dropping* the loser rather than erroring.

### 5.3 YAML version divergence — **[EMPIRICAL], the sharpest finding**

```
$ printf 'no: value\nyes: other\non: third\nversion: 1.10\ncountry: NO\n' > norway.yaml
$ python3 -c "import yaml; print(yaml.safe_load(open('norway.yaml')))"
{False: 'value', True: 'third', 'version': 1.1, 'country': False}
```

Three distinct corruptions in five lines:
1. `no:` and `country: NO` become the boolean `False` (YAML 1.1 booleans).
2. `yes:` and `on:` **both** become the key `True` — two distinct source keys collapse into
   one, silently losing `yes: other`.
3. `version: 1.10` becomes the float `1.1` — a version string is truncated.

Rust's `serde_yaml` is YAML 1.2 core: `parse_bool` accepts only
`true|True|TRUE|false|False|FALSE` (`serde_yaml-0.9.34+deprecated/src/de.rs:932-938`), so
`no`/`yes`/`on`/`off` remain strings.

**Consequence for PACT:** the same authored file yields *different documents* in the Rust
core and a Python adapter. This breaks `AC-1.4` (byte-identical `canonical.json`) and
`AC-7.1` (no silent loss) before the Expansion Rule is even reached. cline already
mitigates this correctly by pinning `yaml.JSON_SCHEMA`
(`cline/…/frontmatter.ts:52`).

**Supply-chain note:** the crate on disk is `serde_yaml-0.9.34+deprecated` — the build
metadata is the author's deprecation marker. A Rust core (D4) needs a maintained YAML 1.2
parser with duplicate-key rejection and an explicit schema.

### 5.4 Binary payloads

**Consistent across the whole corpus: binaries are referenced by path, never inlined.**

- goose collects supporting files and emits them as a *path list* with a resolution hint,
  excluding nested skill dirs (`goose/…/skills/mod.rs:102-132`, `:436-447`).
- continue records `files: [...]` and excludes `SKILL.md` itself
  (`continue/…/loadMarkdownSkills.ts:76-81`).
- Eve classifies non-`skill.md` entries as `skill-resource`
  (`vercel-eve/…/discover/filesystem.ts:281-315`).
- Real binaries ship in skill dirs: `skills-anthropic/skills/theme-factory/theme-showcase.pdf`.
- prompty is the only one that inlines by content type, and it is **explicit**:
  `.json` → parsed, `.yaml` → parsed, **everything else → raw text**
  (`prompty/spec/spec.md:514-516`) — note "raw text", which is wrong for binary.

**Rule:** a directory-expanded field must never inline a non-UTF-8 file. PACT needs a
declared `binary` content kind whose value is `{path, mediaType, digest, size}`, and the
loader must **reject** (not silently mangle) a file that fails UTF-8 validation in a
text-typed slot.

### 5.5 Cycles and symlinks

| Technique | System | Verdict |
|---|---|---|
| Canonicalised visited-set | `goose/…/skills/mod.rs:379-385` | **Correct** |
| Per-path visited list + depth limit 50 | `promptl/src/compiler/scan.ts:587-602`, `constants.ts:25` | **Correct** (for a reference graph) |
| Depth cap only (`MAX_DEPTH = 5`) | `roo-code/…/custom-instructions.ts:46-117` | **Incorrect** — a short symlink loop duplicates content silently |
| Path containment check | `dotprompt/js/src/stores/dir.ts:114-121`; `prompty/spec/spec.md:518-524` | **Correct** |
| None | `goose/…/recipe/template_recipe.rs:124-140` (MiniJinja loader) | **Traversal risk** [INFERRED] |
| Symlinks followed by default | `opencode/…/config/agent.ts:17` (`symlink: true`) | Requires containment check |

### 5.6 Merge semantics

Every system hardcodes merge behaviour per field in code:

- continue: seven named arrays concatenate, `env` spreads, `requestOptions.headers` is
  "the only thing that really merges" (`continue/…/load/merge.ts:11-24`, `:75-84`).
- opencode: deep-merge, arrays replaced, `instructions` concatenated as an explicit
  special case (`opencode/…/config/config.ts:45-51`).
- roo-code: string concatenation with provenance headers
  (`roo-code/…/custom-instructions.ts:187-197`).
- Kustomize: strategy named per patch in the manifest
  (`eval/phoenix/kustomize/auth/kustomization.yaml:3-4`).

**Only Kustomize makes strategy data.** PACT must annotate merge strategy in the schema
(`x-pact-merge: replace | union | concat | unify | error-on-conflict`) so that the loader
is generic and `E-3` ("new authoring surface is free") actually holds.

### 5.7 Case-insensitive filesystems, Unicode, reserved names — **[EMPIRICAL]**

Run on this machine (Linux, ext4):

```
$ touch instructions.md Instructions.md && ls
instructions.md
Instructions.md                      # two distinct files

$ for n in 'a:b' 'a*b' 'CON' 'aux.md' 'a?b' 'a|b' 'a"b' 'trailing.' 'trailing '; do touch "$n"; done
OK for all nine                      # all are illegal or reserved on Windows

$ python3 -c "open('café.md','w'); open('café.md','w'); print([...])"
[b'cafe\xcc\x81.md', b'caf\xc3\xa9.md']   # NFD and NFC coexist as distinct files
```

Implications:

1. A PACT tree containing both `Instructions.md` and `instructions.md` is **valid on Linux
   and unrepresentable on macOS (default APFS) or Windows**. `explode()` therefore cannot
   be total for arbitrary field-name sets — breaking `AC-1.2` unless the field-name →
   filename mapping is restricted.
2. Field names mapping to `CON`, `AUX`, `PRN`, `NUL`, `COM1`…`LPT9`, or names with
   `: * ? | " < > \ /`, or trailing `.`/space, cannot round-trip on Windows.
3. NFC/NFD: an author on macOS may create a directory whose name reads back in a different
   normalisation. cline's `frontmatter.name !== skillName` equality check
   (`cline/…/skills.ts:194`) would then reject a perfectly good skill. **[INFERRED —
   I verified the FS behaviour on Linux; I could not test HFS+/APFS normalisation here.]**
   **No system in the corpus performs any Unicode normalisation** (grep for `NFC`/`NFD`
   across `filedef/*/src` and `filedef/goose/crates` returns nothing).
4. goose's `[a-z0-9-]`, ≤64-char skill-name rule (`goose/…/skills/mod.rs:74-100`) sidesteps
   all of the above and is the pattern to copy for anything that becomes a path segment.

### 5.8 File form vs directory form of the same field

Three different answers, all shipping:

| Policy | System | Evidence |
|---|---|---|
| Both, file first | Eve `instructions.md` + `instructions/` | `vercel-eve/…/grammar.ts:189-190`, `:225-227` |
| Directory wins, file ignored entirely | roo-code `.roo/rules/` vs `.roorules` | `roo-code/…/custom-instructions.ts:223-238` |
| Ordered fallback, first hit only | goose `<name>.yaml` then `<name>.json` | `goose/…/recipe/local_recipes.rs:106-119` |

PACT must pick **one** and make the other an error. The safest is: **both present ⇒ error**,
because it is the only policy under which a reader can predict the value without knowing
the rule.

### 5.9 Editor and OS junk in an expanded directory

roo-code needs a 20-pattern **denylist** to keep `.DS_Store`, `*.swp`, `*.tmp`, `*.bak`,
`Thumbs.db`, `*.pyc`, `*.lock`, `*.crdownload` out of the prompt
(`roo-code/…/custom-instructions.ts:513-548`). Eve keeps a small ignore set
(`.eve`, `.next`, `.output`, `.vercel`, `node_modules` — `vercel-eve/…/filesystem.ts:23-29`).
goose skips only `.git`, `.hg`, `.svn` (`goose/…/skills/mod.rs:363-368`).

A denylist is unbounded; an **allowlist by extension** is not. Eve effectively uses one
for modules (`SUPPORTED_AUTHORED_MODULE_FILE_EXTENSIONS`, `filesystem.ts:7-14`).

### 5.10 Confused deputy / privilege escalation through references

prompty is the only system that states the rule: file references MUST canonicalise, MUST
reject absolute paths, `..`, and symlink escapes; hosts MAY add roots; **"`.prompty`
frontmatter MUST NOT be able to grant itself additional allowed file roots"**
(`prompty/spec/spec.md:518-524`). goose's recipe template loader violates the equivalent
constraint (§2.6.1). PACT is strictly more exposed than either, because learning writes
back spec files (T6/D22) — a poisoned skill that can widen its own read roots is a
self-amplifying compromise.

### 5.11 Path→name derivation is empirically bug-prone

Two shipped bug references found in comments:
- opencode **#25713**: prefix matched anywhere in an absolute path mis-keyed agents whose
  home/parent directories happened to contain `agent/` (`opencode/…/config/entry-name.ts:4-7`).
- cline **#12151**: UTF-8 BOM prevented frontmatter detection
  (`cline/…/frontmatter.ts:38-42`).

---

## 5A. [EMPIRICAL] The shipped PACT loader under 17 adversarial trees **[NEW IN v2]**

v1 could only say what the spec *should* require. There is now an implementation, so v2
measures it. Everything below was run on 2026-08-07 against `target/debug/pact` in this
repository, on Linux 6.11 / ext4, from a baseline workspace that loads cleanly
(`workspace.yaml` + `agents/desk/{agent.yaml,instructions.md}` →
`OK — … loaded cleanly (9 settings)`).

The relevant implementation is `crates/pact-loader/src/lib.rs` (module doc `:1-74`,
classification and folding `:820-923`, `fold_key` `:986-989`) and
`crates/pact-loader/src/policy.rs` (`is_ignored` `:286-304`, `is_self_file` `:326-331`,
`split_ordinal` `:379-396`, `SKIP_DIRS` `:50-51`).

### 5A.0 Scoreboard

| # | Adversarial tree | v1 predicted hazard | Result | Verdict |
|---|---|---|---|---|
| 1 | `instructions.md` **and** `instructions/` | §5.8 | `error loader/duplicate-field` | ✅ correct — v1's recommended "both ⇒ error" policy shipped |
| 2 | `instructions.md` **and** `Instructions.md` | §5.7 | `error loader/duplicate-field` | ✅ correct |
| 3 | `_drafts/` beside `agent.yaml` | §5.9 | `error schema/unknown-field`, fix: "Remove it" | ⚠️ no sigil for "not a field"; see §5A.3 |
| 4 | `.pactignore` at workspace root naming `_drafts` | §5.9 | **still errors** | ⚠️ ignore file is directory-scoped only |
| 4b | `.pactignore` in the same directory | §5.9 | loads cleanly | ✅ works, but undiscoverable |
| 5 | `café.yaml` (NFC) **and** `café.yaml` (NFD) | §5.7 | `error loader/duplicate-field` | ✅ E9 holds — **but the message prints two identical strings** |
| 6 | `con.yaml` as a field | §5.7 | `error schema/unknown-field` | ➖ caught only incidentally (`con` is not a schema field) |
| 7 | `agents/aux/` — Windows reserved **device** name as an agent identity | §5.7 | **loads cleanly** | ❌ unportable tree accepted |
| 8 | `agents/My Desk.v2/` — space, dot, capitals in an identity | §5.7 / AC-1.2′ | **loads cleanly**, id `pact:My Desk.v2` | ❌ no identifier alphabet on the authoritative direction |
| 9 | `instructions/01-a.md` + `instructions/01-b.md` | §4.4 | `error loader/duplicate-order` | ✅ correct — E4 holds |
| 10 | `agents/2024-audit/` + `agents/2025-audit/` | *not predicted* | `error loader/duplicate-field` on key `audit`, with wrong fix text | ❌ ordinal steals an unordered namespace |
| 10b | `agents/2024-audit/` alone | *not predicted* | **loads cleanly as `pact:audit`** | ❌ **BLOCKING** — silent rename of a published identity |
| 11 | `agents/CAFÉ/café.yaml` | *not predicted* | self file not recognised; two spurious `schema/missing-field` errors | ❌ two case-equality functions |
| 12 | invalid UTF-8 in `instructions.md` | §5.4 | `error loader/unreadable`, fix names the encoding menu | ✅ exemplary |
| 13 | `instructions.md` is a symlink | §5.5 | `warning loader/symlink-skipped` | ✅ correct |
| 14 | symlink named `loop` (a kind stem) into its own parent | §5.5 | `error loader/two-self-files` | ⚠️ symlink rule bypassed by the self-file branch |
| 15 | 40-level nesting | §5.5 | `error` naming the depth cap and the path | ✅ correct |
| 16 | `agent.yaml` is a symlink outside the workspace, with a competing `instructions.md` | §5.10 | `error loader/ambiguous-field` — *proving the outside file was read* | ❌ |
| 16b | `agent.yaml` is a symlink outside the workspace, alone | §5.10 | **`OK — loaded cleanly (9 settings)`**, identity/instructions taken from outside the tree | ❌ **BLOCKING** |
| 17 | whole agent folder is a symlink outside | §5.5 | `warning loader/symlink-skipped` | ✅ correct |

**6 of 9 v1-predicted hazards are correctly handled. Three defects are new findings.**

### 5A.1 / 5A.2 File-vs-directory and case collisions — correct

```
$ pact check t1                       # instructions.md + instructions/
error: 'instructions.md' and 'instructions' would both become the setting 'instructions'.
  fix: Rename one of them. Two files can't describe the same setting, and names that
       differ only by capitalisation clash on some computers.
  rule: loader/duplicate-field
```

v1 §5.8 argued for "both present ⇒ error" over Eve's "both, file first"
(`vercel-eve/…/grammar.ts:189-190`) and roo-code's "directory wins"
(`roo-code/…/custom-instructions.ts:223-238`). That is what shipped. Keep it.

### 5A.3 / 5A.4 There is no sigil for "this folder is not a field"

```
$ pact check t3                       # agents/desk/_drafts/a.yaml
error: '_drafts' is not something an agent can have.
  fix: Remove it, or use one of: name, description, instructions, team, teamwork, uses, …
  rule: schema/unknown-field
```

`Policy::is_ignored` (`policy.rs:286-292`) ignores exactly two classes: names starting with
`.`, and the six-name `SKIP_DIRS` denylist (`policy.rs:50-51`:
`node_modules, target, __pycache__, venv, dist, build`). Everything else is a field, and an
unrecognised field is a hard error.

The only zero-config escapes are therefore **(a) make the folder hidden** (`.drafts/`) or
**(b) write a `.pactignore` in that same directory** — a root `.pactignore` naming `_drafts`
did **not** rescue it (§5A.4), only a colocated one did (§5A.4b).

Both escapes fail D13's audience test. A non-technical domain expert does not know that a
leading dot hides a folder from their own file manager, and will not discover a dotfile
format. Next.js's answer — `_`-prefix means "private", one character, no configuration
(`route-discovery.ts:99`) — is strictly better for this audience, and PACT has *already
half-claimed* `_` for `_index` self files (`policy.rs:327`), so the character is neither
free nor reserved. This is the sigil-alphabet decision (§0.2 item 6) in its most concrete
form.

### 5A.5 NFC/NFD is detected, and the message is unactionable

```
$ ls t5/agents/desk | cat -v
cafeM-LM-^A.yaml            # NFD:  c a f e U+0301
cafM-CM-).yaml              # NFC:  c a f U+00E9
$ pact check t5
error: 'café.yaml' and 'café.yaml' would both become the setting 'café'.
  note: the other one (…/agents/desk/café.yaml:1:1)
  fix: Rename one of them. …
```

E9 fires correctly (`fold_key`, `lib.rs:986-989`). But the diagnostic renders **two
byte-different names as two identical glyph sequences**, and the `-->` and `note:` paths are
also visually identical. The author cannot act on this. O7.3 requires that every error name
the file and the fix; here it names two files the reader cannot distinguish. Fix: when two
colliding names are equal after NFC but differ in bytes, print the escaped form
(`cafe\u{301}.yaml` vs `caf\u{e9}.yaml`) and say "these differ only in how the accent is
stored".

Note also that this tree produced **two errors for one mistake** — a `schema/unknown-field`
for `café` *before* the `loader/duplicate-field` — because schema validation of the winner
runs regardless of the loader conflict.

### 5A.7 / 5A.8 Author-chosen identities are not constrained at all

```
$ pact check t7b      # agents/aux/  and  "agents/My Desk.v2/"
OK — … loaded cleanly (17 settings).
$ pact discover t7b | grep '"id"'
        "id": "pact:My Desk.v2",
        "id": "pact:aux",
```

Two distinct failures of AC-1.2′ / P-5, both on the direction D2 declares authoritative:

- `agents/aux/` cannot be checked out on Windows at all (`AUX` is a reserved device name);
  the tree is unclonable, not merely awkward.
- `pact:My Desk.v2` becomes the agent's **published identity**, flowing into `pact discover`
  output and thence, per O6.1–O6.3, into the Bud `AgentRecord`, the A2A Agent Card, and the
  OSSA manifest. A space in an identifier that lands in a URI or a registry coordinate is a
  downstream escaping problem PACT is exporting to every consumer.

The thesis already states the alphabet (`^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$`, ≤64 bytes, NFC,
no Windows device names, AC-1.2′) and requires `explode` to fail loudly outside it. **The
constraint is written for the derived direction and absent from the native one.** goose
already does the right thing for the same construct — skill names are `[a-z0-9-]`, ≤64, no
leading/trailing hyphen, enforced at load (`goose/crates/goose/src/skills/mod.rs:74-100`).

### 5A.10 The ordinal prefix steals every unordered namespace — **BLOCKING**

```rust
// crates/pact-loader/src/policy.rs:379-396
pub fn split_ordinal(stem: &str) -> (Option<u32>, &str) {
    let digits_end = stem.find(|c: char| !c.is_ascii_digit()).unwrap_or(stem.len());
    if digits_end == 0 || digits_end == stem.len() { return (None, stem); }
    let sep = stem.as_bytes()[digits_end];
    if sep != b'-' && sep != b'_' { return (None, stem); }
    …
    match stem[..digits_end].parse::<u32>() { Ok(n) => (Some(n), rest), … }
}
```

The split is applied to **every** directory entry in `Loader::entries`
(`lib.rs:823`), before any knowledge of whether the containing field is ordered. So:

```
$ pact check t10b                    # agents/2024-audit/agent.yaml, nothing else
OK — … loaded cleanly (13 settings).
$ pact discover t10b | grep -E '"id"|"path"'
        "id": "pact:audit",
        "path": …/agents/2024-audit/agent.yaml
```

The folder says `2024-audit`. The identity says `audit`. Nothing says anything happened.
That is a silent semantic transformation of a **published identifier**, which T7 ("no silent
degradation anywhere") and AC-7.1 ("a fuzzer … finds no path where a semantic element
vanishes without a report entry") both forbid.

With two such folders it becomes a refusal with misleading advice:

```
$ pact check t10                     # agents/2024-audit/ + agents/2025-audit/
error: '2025-audit' and '2024-audit' would both become the setting 'audit'.
  fix: Rename one of them. Two files can't describe the same setting, and names that
       differ only by capitalisation clash on some computers.
```

The names do not differ by capitalisation. The `loader/duplicate-field` fix string is
written for the case-collision cause and is reused for the ordinal cause.

Affected namespaces are every map with author-chosen keys: `agents/`, `team:`, `remembers:`,
`variants:`, `uses:`, `tools/`, `evals` cases, `policies/`, `loops/`. Realistic collisions
are not exotic — `2024-audit`, `2025-audit`, `1099-forms`, `24-hour-desk`, `401k-helper`,
`10-k-filings` all lose their prefix. `split_ordinal`'s own tests show the authors thought
about `3d-model` and `v2-agent` (`policy.rs:404-413`) but not about a name that legitimately
*starts* with digits and a hyphen.

Note the escape that already exists and is untaken: `split_ordinal("2024")` returns
`(None, "2024")` — a bare number is a name (`policy.rs:407`). So the rule is already
field-sensitive in spirit; it just is not field-sensitive in fact.

### 5A.11 Two case-equality functions

```
$ ls t11/agents/CAFÉ | cat -v
cafM-CM-).yaml                       # café.yaml, NFC
$ pact check t11
error: An agent must have a 'description'.  --> …/agents/CAFÉ
  fix: Create …/agents/CAFÉ/agent.yaml and put one line in it: `description: ...`
error: An agent must have 'instructions'.   --> …/agents/CAFÉ
```

`is_self_file` (`policy.rs:326-331`) asks `stem.eq_ignore_ascii_case(dir_name)`. ASCII case
folding leaves `É` (U+00C9) and `é` (U+00E9) distinct, so `café.yaml` is not the self file of
`CAFÉ/`; it becomes an ordinary field named `café`, the agent has no self file, and the
author is told to write the file they already wrote. Meanwhile `fold_key`
(`lib.rs:986-989`) — the function the *same loader* uses for field identity — would have
called those two keys equal.

`Policy::is_ignored` and `Policy::file_kind` add a third variant, `to_ascii_lowercase`
(`policy.rs:268`, `:294`, `:300`, `:347`).

**One rule, one function.** Whatever equality PACT chooses for names, `is_self_file`,
`is_ignored`, `file_kind` and `fold_key` must all call it. The choice should be at least as
coarse as the coarsest filesystem PACT claims to support, or two files that PACT thinks are
distinct cannot coexist on macOS/Windows.

### 5A.14 / 5A.16 The symlink refusal does not cover self files — **BLOCKING**

The module doc states the invariant plainly:

> A spec tree is a supply-chain surface and a link can point anywhere, so the answer is the
> same at the top of an ordinary folder (`Loader::load_path`) and inside an attachment
> folder (`Loader::walk_payload`). … A link is refused for BEING a link, not for where it
> points. — `crates/pact-loader/src/lib.rs:141-154`

It is not the same answer. In `Loader::entries` the self-file test runs *first*
(`lib.rs:826` — `if !is_dir && self.policy.is_self_file(dir_name, key)`), and the entry is
consumed into `self_file` before anything asks whether it is a link.

```
$ ls -l t16b/agents/desk/agent.yaml
agent.yaml -> /…/scratchpad/outside/evil.yaml
$ pact check t16b
OK — … loaded cleanly (9 settings).
$ pact discover t16b | grep -E '"id"|"name"|"description"'
        "id": "pact:desk",
        "name": "Evil",
        "description": "An agent definition living outside the workspace tree.",
```

Zero warnings. The agent's identity, description and instructions come from a file that is
not in the workspace and was not reviewed with it. Corroborating evidence that the link is
genuinely followed rather than defaulted: with a competing `instructions.md` present, the
loader reports `loader/ambiguous-field` naming *the symlinked `agent.yaml`'s line 3* as the
other definition site (§5A.16) — it parsed the outside file.

By contrast a symlinked **field** file (§5A.13) and a symlinked **directory** (§5A.17) both
produce `loader/symlink-skipped` correctly, and §5A.14 shows a third behaviour: a symlink
named `loop` (a kind stem, so `is_self_file` matches) is reported as
`loader/two-self-files` — "This folder has two files describing itself: 'agent.yaml' and
'loop'. fix: Keep only one of them." Three inputs of one kind, three different answers.

**Severity.** Git preserves symlinks. A pull request that adds one symlink under
`agents/x/` is a one-line diff that a reviewer sees as "added agent.yaml", and it can source
the agent's instructions from outside the reviewed tree. Under T6/D22 — learning writes spec
files back — the write side inherits the same escape. prompty is the only system in the
corpus that writes the correct rule down, and it is worth quoting as the target:
"Implementations MUST resolve the target to its canonical path before reading … MUST reject
absolute paths, `..` traversal, and symlink escapes that resolve outside the containing
`.prompty` file's directory tree … `.prompty` frontmatter MUST NOT be able to grant itself
additional allowed file roots" (`prompty/spec/spec.md:518-524`, verbatim, re-read
2026-08-07).

### 5A.12 / 5A.15 What is exemplary and should be held as the bar

```
error: '…/instructions.md' is not saved as plain UTF-8 text.
  fix: Re-save it from your editor choosing UTF-8 (in most editors: File → Save As →
       Encoding: UTF-8). If it is an image, sound or other non-text file, give it its
       proper file extension instead.
  rule: loader/unreadable
```

This is what O7.3 looks like when it is done: the rule, the file, the cause, and two
alternative fixes phrased for someone who does not know what UTF-8 is. The depth-cap message
(§5A.15) similarly names the path *and* the likely cause ("This usually means a folder links
back into itself"). The three defects above are not a quality problem in this loader; they
are three specific holes in an otherwise unusually careful implementation.

---

## 6. Verdict on T5 (the Expansion Rule)

### 6.1 Verdict

**T5 is sound, and it is materially stronger than Eve's slot table — but only under four
restrictions, each of which must be normative text, not implementation detail.**

The rule as stated in `00-THESIS.md:75-76` — *"any field of a document may be written as a
directory, and any directory is exactly a field"* — is **not** well-defined as written,
because it does not say what function maps N filesystem children to one field value. The
corpus shows that when that function is left implicit, implementations pick different ones
and diverge (§3.1, §3.3, §2.3). CUE shows the function must be a lattice meet for the rule
to be order-independent (`config/cue/doc/ref/spec.md:670-674`).

**Restated soundly:**

> **Expansion Rule (normative form).** For every field `f` of type `T` in the PACT schema,
> the schema defines exactly one **expansion form** `E(f)` — a file or a directory — and one
> **fold** `⊕_T` from the expansion's children to a value of type `T`. The fold is required
> to be **deterministic, total, and independent of filesystem enumeration order**. For
> unordered composite types `⊕_T` is *unification* (commutative, associative, idempotent,
> conflict ⇒ error). For ordered types, `⊕_T` is defined only when order is carried
> **in-band** (a manifest, an explicit `order:` key, or a zero-padded numeric filename
> prefix); otherwise the directory form is **not available** for that field and the loader
> must say so.

### 6.2 What this buys over Eve, concretely

- Eve maintains **four** hand-written classification tables
  (`vercel-eve/…/discover/filesystem.ts:120-205`, `:208-278`, `:281-315`, `:318-336`).
  Under the restated rule the classifier is one function of the schema, satisfying `E-3`.
- Eve's slot list has no `evals`, `variants`, `contract`, `loop`, `policies`, or `models`
  slot; adding any requires editing all four tables plus their discover functions.
  PACT gets them by declaring fields.
- Eve's ordering is `localeCompare` (`grammar.ts:176`); the restated rule forbids it.

### 6.3 What T5 must give up

1. **`explode` cannot be total.** §5.7 proves a field-name alphabet exists that no
   cross-platform filesystem can represent. `AC-1.2` must be restated as: *for all specs
   whose field names and identifiers lie in the portable alphabet*, `explode ∘ collapse = id`;
   for the rest, `explode` must **fail loudly** with the offending name.
2. **Ordered fields do not get a free directory form.** Lists are the majority of PACT's
   interesting content (loop steps, topology edges, eval cases, tool lists). Pkl shows why
   (`config/pkl/…/index.adoc:1391-1404`). Either they carry order in-band or they stay
   single-file. This is the largest scope reduction the evidence forces.
3. **Comments and key order are not preserved through a machine write** (cline
   `skills.ts:58-61`). D18's four author surfaces therefore need an explicit statement of
   what a UI write is allowed to destroy.

### 6.4 Answer to the central question

> *Is there a defensible general rule that unifies "a directory is a field"?*

**Yes — with a precedent that predates the agent industry.** The rule is CUE's
package/instance model: a directory is one value; the children are combined by a lattice
meet; order is irrelevant *because the operator makes it irrelevant*; conflicts are errors,
not overrides. Every failure in the agent-tooling corpus traces to using a non-commutative
combiner (last-wins, first-wins, concatenate) while pretending the filesystem supplies a
canonical order it does not have.

### 6.5 **[v2]** The rule is sound; the *naming layer* is where it actually breaks

v1 located the danger in the fold (`⊕_T`) and was right to. Having now measured a real
implementation that gets the fold right, the residual failures are all in a layer v1 treated
as trivial: **the function from a directory entry's name to a field key.**

`name → key` is not the identity. In the shipped loader it is, in order:

```
strip extension  →  split_ordinal  →  is_self_file?  →  fold_key (NFC ∘ lowercase)
```

Four transformations, three of which can change or consume the author's chosen name, and
each of which was introduced for an independently good reason. Every one of §0.2's items
7, 9 and 11 is a collision *between two of these transformations*, not a flaw in any one of
them:

| Interaction | Symptom |
|---|---|
| `split_ordinal` × unordered map | `2024-audit` → `audit`, silently (§5A.10) |
| `is_self_file` × `fold_key` | two case-equality functions disagree (§5A.11) |
| `split_ordinal` × `fold_key` error text | collision reported with case-collision advice (§5A.10) |
| extension strip × slot identity | `page.ts` + `page.tsx` in Next.js; PACT errors correctly (§5A.1) |

So the corrected statement of the rule is:

> **Typed Expansion (v2).** A directory is a field, *and the mapping from entry name to
> field key is part of the schema, not part of the loader.* For each field the schema
> declares (a) the **expansion form** (`file | dir | payload | none`), (b) the **fold**
> (`unify | set | map(key) | sequence`), and (c) the **name grammar** that entry names in
> that expansion must satisfy. Ordinal prefixes are legal **only** where the fold is
> `sequence`. Name equality is one function, used everywhere.

This is a strictly stronger claim than v1's, and it is the one the evidence supports:
Next.js needed sigils because names are overloaded (§2.16.2); Kubernetes needed `listMapKey`
because "which name identifies this element" is a per-field question (§4.6a); dotprompt and
genkit diverged because `.` meant two things in one name (§2.3); PACT's ordinal steals a
namespace because the name transformation is global where the schema is local (§5A.10).

### 6.6 **[v2]** What T5 must additionally give up or reserve

Adding to §6.3's three:

4. **The ordinal prefix is not free.** It must be scoped to `sequence` fields, or it is a
   silent rename everywhere else. Kubernetes' `listType: map` + `listMapKey` (§4.6a) shows
   most "ordered" collections are keyed, not ordered, so this scoping costs less than it
   looks.
5. **A sigil alphabet must be reserved in `v1` even if unused.** Next.js needed
   "organise without naming" (`(group)`), "this directory is a named field rather than a
   segment" (`@slot`) and "not part of the document" (`_private`). PACT today has no
   grouping, a half-claimed `_`, and a claimed leading-`NN-`. Adding grouping later changes
   the identity of existing trees. Reserve leading `(`, `@`, `_`, and leading-digit-plus-
   separator now; refuse them in author-chosen names; define at most one of them in v1.
6. **The identifier alphabet must be enforced on the *tree*, not only on `explode`.** D2
   makes the tree authoritative, so AC-1.2′'s portable key alphabet has to be a load-time
   check on directory and file names, not a serialisation-time check. Otherwise PACT accepts
   trees that cannot be cloned on Windows (§5A.7) and mints registry identities containing
   spaces (§5A.8).

---

## 7. What the normative algorithm must specify

This is the checklist for the loader section of `20-ARCHITECTURE`. Each item exists because
something in §5 breaks without it.

> **[v2 status]** Items measured against the shipped loader on 2026-08-07 are marked
> ✅ (implemented and verified), ⚠️ (partial), ❌ (absent or defective, with the §5A test that
> shows it), or ➖ (not measured). Twelve new items **N1–N9** are appended in §7-bis; they
> come from evidence that did not exist when this list was written.

**A. Encoding and text**
1. Files MUST be UTF-8. A leading BOM (`U+FEFF`) MUST be stripped before any parse
   (cline `frontmatter.ts:38-42`). Invalid UTF-8 in a text-typed slot is an error, not a
   lossy decode.
2. Line endings: `\r\n`, `\r`, `\n` all accepted; normalised to `\n` before hashing
   (dotprompt `js/src/parse.ts:67-68`; picoschema `spec/picoschema.yaml:410`).
3. Path components MUST be compared after Unicode **NFC** normalisation; the canonical form
   stored in `canonical.json` is NFC.

**B. YAML dialect**
4. PACT YAML is **YAML 1.2 core schema only**. `yes/no/on/off` are strings. `y/n` are
   strings. Sexagesimals and octal-by-leading-zero are not special.
5. **Duplicate mapping keys are an error**, at every nesting level (OCI I-JSON parallel,
   `protocols/oci-image-spec/considerations.md:33`).
6. Merge keys (`<<:`), anchors/aliases: either forbidden or bounded — if permitted, alias
   expansion MUST be depth- and size-capped, and the canonicaliser MUST emit the expanded
   form.
7. Scalars that look like versions (`1.10`) MUST NOT be coerced to numbers in fields typed
   as version strings; the schema type governs, not the YAML tag.

**C. Frontmatter**
8. The delimiter is `---` at the **very start of the document** (after optional BOM), on its
   own line; the closing `---` is the next line consisting solely of `---`. Publish
   normative test vectors as prompty does (`prompty/spec/spec.md:201-223`) — at minimum:
   no frontmatter; empty frontmatter; body containing `---`; body containing two `---`;
   CRLF; BOM; leading blank lines; frontmatter that is a scalar not a mapping.
9. Frontmatter present but unparseable ⇒ **error naming file, line, column, rule, fix**
   (`O7.3`). Never fail-open (dotprompt `js/src/parse.ts:230-233` is the anti-pattern).
10. Frontmatter that parses to a non-mapping ⇒ error (`prompty/spec/spec.md:861-862`).

**D. Discovery and identity**
11. Enumerate roots in a **stated, fixed order**; `pact explain` MUST print the ordered root
    list with existence markers (aider `main.py:492-496`).
12. Within a directory, sort entries by the **UTF-8 byte sequence of the full path relative
    to the expansion root**. `localeCompare`, locale collation, and case folding are
    forbidden.
13. Identity: the **path is authoritative**; a frontmatter `name` that disagrees with the
    path is an **error**, not a warning and not an override. (Chosen over goose's
    frontmatter-wins because D2 makes the tree the source of truth; the check must compare
    NFC-normalised, case-sensitively.)
14. Identifiers that become path segments MUST match `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`,
    length ≤ 64 (goose `skills/mod.rs:74-100`), and MUST NOT be a Windows reserved device
    name. Field names outside this alphabet MUST use an escape encoding, and `explode` MUST
    fail loudly on names that cannot be escaped.
15. Two entries resolving to the same logical identity ⇒ **error listing both paths**.
    Never first-wins, never last-wins.

**E. Expansion**
16. For every schema field, exactly one expansion form and one fold, both declared in the
    schema (`x-pact-expand: file | dir | none`, `x-pact-merge: unify | replace | concat | union`).
17. **File form and directory form of the same field both present ⇒ error** naming both.
18. Text-typed directory expansion: children are joined with a **stated separator** and each
    contributes a **provenance record** `{path, digest, byteRange}` in the derived index.
    (roo-code emits provenance into the prompt text itself,
    `custom-instructions.ts:187-197`; PACT should emit it out-of-band so the value stays
    clean.)
19. Ordered fields: the directory form requires in-band order. Specify **one** mechanism
    (recommendation: zero-padded numeric prefix `NN-name.ext`, prefix stripped from the
    identity, ties ⇒ error). Absent that, the directory form is unavailable and the loader
    says which field and why.
20. Non-text leaves: a `binary` content kind whose value is `{path, mediaType, digest, size}`.
    Never inline. Never UTF-8-decode.
21. Inclusion is by **extension allowlist per field type**, not by junk denylist. Files in
    an expansion directory that match no allowlist entry ⇒ diagnostic (warning at L0,
    error under `--strict`), never silent skip.
22. Dotfiles and dot-directories in an expansion directory are ignored, with the ignore
    list published and closed.

**F. References, symlinks, containment**
23. Every reference (`$ref`, `${file:}`, include, subagent path, sub-recipe path) MUST be
    resolved to a canonical path and MUST be contained by an allowed root. Roots come from
    the invoking host; **a spec file MUST NOT be able to add a root**
    (`prompty/spec/spec.md:524`).
24. Symlinks: resolve, then containment-check the target. Cycle protection is a
    **canonicalised visited set** (goose `skills/mod.rs:379-385`), not a depth cap.
    A cycle is an error naming the cycle, not a truncation.
25. Reference graphs additionally carry a depth limit with a typed error
    (promptl `constants.ts:25`, `errors.ts:213-215`).
26. Referenced-document parameters must be satisfied at the reference site
    (promptl `scan.ts:633-640`).

**G. Canonicalisation, digests, versioning**
27. `canonical.json` MUST be I-JSON: UTF-8, no duplicate names, numbers within IEEE-754
    double, and serialised per RFC 8785 so the digest is stable
    (`protocols/oci-image-spec/considerations.md:29-36`).
28. Every node carries a **transitive** content digest: `H(own bytes ‖ digests of children
    and references)` (promptl `scan.ts:170-172`, `:655`). `pact.lock` pins the root digest.
29. `apiVersion: pact.dev/v1` MUST be present. Import compatibility is **graded**, not
    boolean: `ok | warnings | needs-confirmation | failed`, per dify
    (`api/services/dsl_version.py:5-19`). Missing version ⇒ **error**, never a silent
    default (dify `app_dsl_service.py:192-196` is the anti-pattern).
30. Deprecated-field migration runs as a **decode-time normalise transform** so old trees
    load and re-serialise forward (opencode `core/src/v1/config/agent.ts:62-79`;
    roo-code `mode.ts:81-89`). Every applied migration appears in the report.

**H. Errors and reporting**
31. Every diagnostic carries `{file, line, column, rule-id, message, fix}` (`O7.3`).
32. Unknown keys are rejected at every level with the offending key list
    (opencode `config/parse.ts:34-55`); `x-`-prefixed keys round-trip untouched
    (`AC-1.3`). Note prompty had to be permissive (`spec/spec.md:242-243`) *because* it
    lacks an extension namespace — PACT's `x-` is what makes strictness affordable.
33. Every skipped file, resolved override, applied migration, and stripped junk entry is a
    line in the load report. `AC-7.1` is unachievable if the loader can drop anything
    silently — and five of the surveyed systems drop silently
    (dotprompt `parse.ts:221-228`; genkit `prompt.ts:846-850`; opencode `config/agent.ts:29`;
    continue `blockDuplicationDetector.ts:29-36`; goose `skills/mod.rs:433-451`).

---

## 7-bis. **[v2]** Additional normative requirements, from measured evidence

**N1 — One name-equality function.** Define `key_eq(a, b)` once. `is_self_file`,
`is_ignored`, `file_kind`, duplicate detection and reference resolution MUST all call it.
Today there are three (`fold_key` NFC∘Unicode-lowercase, `eq_ignore_ascii_case`,
`to_ascii_lowercase`) and the disagreement is author-visible (§5A.11). Recommended
definition: `NFC → Unicode simple case-fold → reject if the result collides with another
entry`. Add Next.js's punctuation rule (`validate-app-paths.ts:104-114`) if PACT wants
`refund-desk` and `refund_desk` to collide, which it should for identities that reach a
registry.

**N2 — Name→key transformation is schema-scoped, not global.** `split_ordinal` MUST run
only where the schema declares the fold `sequence`. Everywhere else the entry name is the
key, verbatim after extension strip (§5A.10; §6.5).

**N3 — Collection kinds are declared.** Each collection field declares
`set | map(key) | sequence`, per Kubernetes `listType`/`listMapKey`
(`config/kubevela/…/crds/bucket.yaml:141-144`). Only `sequence` admits ordinal prefixes;
`map(key)` gets its directory form for free with entry-name-as-key (§4.6a).

**N4 — The symlink rule is applied before classification, with no exceptions.** A directory
entry MUST be tested for `is_symlink` before it is tested for self-file-ness, field-ness, or
payload-ness. Today the self-file branch runs first and a symlinked `agent.yaml` pointing
outside the workspace loads with zero diagnostics (§5A.16b). If PACT ever chooses to follow
links, it MUST adopt prompty's containment rules verbatim
(`prompty/spec/spec.md:518-524`) — canonicalise, reject absolute and `..`, reject escapes,
and forbid a spec file from adding its own roots.

**N5 — Identifier alphabet enforced on load.** Every directory or file name that becomes a
field key or a published identity MUST match the portable alphabet of AC-1.2′ and MUST NOT
be a Windows reserved device name (`CON AUX PRN NUL COM1-9 LPT1-9`, with or without
extension) nor end in `.` or space. Enforced at `pact check`, not only at `explode`
(§5A.7, §5A.8). Precedent: goose (`skills/mod.rs:74-100`).

**N6 — Reserve the sigil alphabet.** Leading `(`, `@`, `_`, and `<digits><-|_>` are reserved
in author-chosen names in `v1`. Define at most one meaning now (recommendation: `_` = "not
part of the document", matching Next.js `route-discovery.ts:99` and freeing the non-technical
author from `.pactignore` and from hidden files, §5A.3). Reserving is cheap; retrofitting
changes existing identities.

**N7 — Enumerate, never probe.** Field resolution MUST be by enumerating a directory and
folding entry names, never by opening a constructed filename. Where PACT must resolve a
*written* path (`evals:`, `loop:`, `policy:`, `.pactignore`), it MUST perform a true-case
check — re-enumerate the parent and require exact membership — per Next.js
`isTrueCasePagePath` (`find-page-file.ts:12-21`). Otherwise a reference written
`evals: /Evals/Suite.yaml` resolves on macOS and fails in CI.

**N8 — Collision diagnostics must be readable.** When two colliding names are equal after
normalisation but differ in bytes, the message MUST render them distinguishably (escaped
code points) and MUST name the actual cause. Today an NFC/NFD collision prints the same
glyph sequence twice (§5A.5) and an ordinal collision is explained as a capitalisation
clash (§5A.10). Each distinct collision cause needs its own rule id and fix text:
`loader/duplicate-field` (case), `loader/duplicate-field-normalisation` (NFC/NFD),
`loader/ordinal-collision`, `loader/duplicate-order`.

**N9 — One mistake, one message.** A tree with one defect currently emits two errors when
the loader conflict and the schema check both fire on the same entry (§5A.5). Schema
validation of an entry SHOULD be suppressed when that entry is already the subject of a
loader-level refusal.

---

## 8. Open questions for the architecture phase

1. **Ordered-field directory form.** Numeric prefix, `_order.yaml` manifest (Kustomize's
   `resources:`), or "no directory form"? Kustomize's explicit list is the most robust but
   costs the no-code audience an extra file. Needs a D13/D14 usability decision.
2. **Identity: path vs frontmatter.** I recommend path-authoritative (§7.13) on D2 grounds,
   but it conflicts with the de-facto Agent Skills behaviour in goose
   (`skills/mod.rs:235-248`), which PACT must import from (`AC-6.4`). Import may need a
   rename-with-report path.
3. **Which YAML parser for the Rust core.** `serde_yaml` is deprecated (crate on disk is
   `0.9.34+deprecated`) and its `Value` path errors on duplicate keys while its struct path
   errors on duplicate fields — behaviour PACT wants, but on an unmaintained dependency.
4. **Python-side parser conformance.** Given §5.3, PACT must ship a conformance test that a
   provider process's YAML parse of the same bytes yields the same canonical document, or
   forbid providers from parsing spec YAML at all (they receive `canonical.json` instead —
   consistent with `P-1`).
5. **Case-insensitive-filesystem policy.** Reject at `pact validate` any tree containing two
   paths that case-fold equal (portable), or only warn (permissive)? Portability argues
   reject; it makes some valid Linux trees invalid.
6. **AGENTS.md.** Import-only hint, or a first-class instruction source? If the latter,
   PACT must choose between "nearest wins" (`agents-md/components/HowToUseSection.tsx:34-39`)
   and "concatenate all" (`roo-code/…/custom-instructions.ts:355-378`) and say so.
7. **Agent Skills spec is not offline-resolvable** (`skills-anthropic/spec/agent-skills-spec.md:1-3`).
   Under D17, PACT must vendor its own normative restatement of the SKILL.md format and
   treat agentskills.io as informative.
8. **Merge-strategy vocabulary.** `unify | replace | concat | union | error-on-conflict` is
   my proposal from §5.6; the closed set needs ratification against the actual field list
   once `pact.dev/v1` is drafted.
9. **Colocated-glob rebasing.** continue rewrites a rule's globs relative to its directory
   (`markdownToRule.ts:71-93`). Does PACT do the same for path-scoped policies/hooks? It
   is ergonomic and it is a hidden semantic that depends on file location.
10. **Preserving trivia on machine writes** (D18 UI + T6 learning). cline's rewrite drops
    comments and key order (`skills.ts:58-61`). Needs either a round-tripping YAML writer
    or an explicit "machine writes normalise" rule with a `pact fmt` to make it uniform.

---

### 8-bis. **[v2]** Open questions raised by the new evidence

11. **Does PACT want an organisational grouping sigil at all?** `agents/finance/refund-desk/`
    is refused today (`crates/pact-cli/tests/the_workspace_a_check_finds_is_the_workspace_a_runtime_finds.rs:419-451`).
    With 3 agents that is fine; with 40 it is the flat-namespace problem Next.js fixed with
    `(group)`. Deciding "no grouping, ever" is acceptable — deciding it *by default, by not
    reserving the character* is not.
12. **Which case-fold?** Unicode simple fold, full fold, or ASCII-only? Full folding maps
    `ß → ss`, which no filesystem in common use does; ASCII-only under-approximates macOS.
    Whatever is chosen, the answer must be one function (N1) and must be *at least as coarse*
    as the coarsest supported filesystem, so PACT never accepts a tree that cannot be
    checked out.
13. **Should `pact check` refuse an unclonable tree, or warn?** `agents/aux/` is valid on
    Linux and impossible on Windows. Refusing makes some valid Linux trees invalid;
    warning means CI on Linux passes and a Windows contributor cannot clone. Given D17
    (all four deployment targets) and D18 (four author surfaces), refusal seems right, with
    an explicit `--allow-unportable-names` recorded in the report per T7.
14. **Where does the ordinal live once N2 scopes it?** If only `sequence` fields admit
    `NN-`, an author who numbers files in a `map` field gets an error naming a rule they did
    not know existed. The error text must say "this list is not ordered; the number is part
    of the name" and offer the rename.
15. **Is `.pactignore` the right escape at all?** It is directory-scoped (§5A.4 vs §5A.4b),
    which is surprising, undocumented in the CLI help path I read, and unreachable for the
    D13 audience. A `_` sigil (N6) would make it unnecessary for the common case.

---

## Appendix A — commands run for the [EMPIRICAL] results

```
printf 'name: a\nname: b\n' > dup.yaml
python3 -c "import yaml; print(yaml.safe_load(open('dup.yaml')))"
# → {'name': 'b'}

printf 'no: value\nyes: other\non: third\nversion: 1.10\ncountry: NO\n' > norway.yaml
python3 -c "import yaml; print(yaml.safe_load(open('norway.yaml')))"
# → {False: 'value', True: 'third', 'version': 1.1, 'country': False}

mkdir fstest && cd fstest
touch instructions.md Instructions.md && ls
# → both files present (case-sensitive ext4)

for n in 'a:b' 'a*b' 'CON' 'aux.md' 'a?b' 'a|b' 'a"b' 'trailing.' 'trailing '; do touch "$n"; done
# → all nine succeed on Linux; all nine are illegal or reserved on Windows

python3 -c "open('café.md','w'); open('café.md','w'); import os; print([n.encode() for n in os.listdir('.') if b'caf' in n.encode()])"
# → [b'cafe\xcc\x81.md', b'caf\xc3\xa9.md']  (NFD and NFC are distinct files on Linux)
```

Environment: Linux 6.11.0, ext4, Python 3 + PyYAML, Node v24.15.0,
`serde_yaml-0.9.34+deprecated` from the local cargo registry.

### Appendix A-bis — **[v2]** the 17 adversarial trees (§5A)

Baseline `fs1`: `workspace.yaml` (copied from `examples/answers-from-documents/`) +
`agents/desk/agent.yaml` (`name`, `description`) + `agents/desk/instructions.md`.
Each test copies `fs1`, mutates it, and runs `target/debug/pact check` (and `discover`
where identity is the question).

```bash
B=$PWD/target/debug/pact                       # agent-inter-op @ master, 2026-08-07
mk(){ rm -rf $S/$1; cp -r $S/fs1 $S/$1; }

# 1  file form AND directory form of one field
mk t1;  mkdir -p $S/t1/agents/desk/instructions; echo More. > $S/t1/agents/desk/instructions/extra.md
# 2  case-only sibling
mk t2;  echo Other. > $S/t2/agents/desk/Instructions.md
# 3  underscore folder                          4  root .pactignore   4b colocated .pactignore
mk t3;  mkdir -p $S/t3/agents/desk/_drafts; echo 'x: 1' > $S/t3/agents/desk/_drafts/a.yaml
# 5  NFC vs NFD siblings
mk t5;  printf 'x: 1\n' > "$S/t5/agents/desk/$(printf 'caf\xc3\xa9').yaml"
        printf 'x: 2\n' > "$S/t5/agents/desk/$(printf 'cafe\xcc\x81').yaml"
# 6  reserved device name as a field            7 as an agent identity
mk t6;  echo 'x: 1' > $S/t6/agents/desk/con.yaml
mk t7b; mkdir -p $S/t7b/agents/aux "$S/t7b/agents/My Desk.v2"     # + name/description/instructions
# 9  ordinal tie
mk t9;  rm $S/t9/agents/desk/instructions.md; mkdir -p $S/t9/agents/desk/instructions
        echo A > $S/t9/agents/desk/instructions/01-a.md; echo B > $S/t9/agents/desk/instructions/01-b.md
# 10 / 10b  digit-prefixed agent folders
mk t10; mkdir -p $S/t10/agents/2024-audit $S/t10/agents/2025-audit    # + agent.yaml in each
mk t10b; mkdir -p $S/t10b/agents/2024-audit
# 11 non-ASCII case self file
mk t11; mkdir -p "$S/t11/agents/$(printf 'CAF\xc3\x89')"
        printf 'name: C\ndescription: …\ninstructions: Hi.\n' > "$S/t11/agents/$(printf 'CAF\xc3\x89')/$(printf 'caf\xc3\xa9').yaml"
# 12 invalid UTF-8 in a text slot
mk t12; printf 'Be helpful \xff\xfe\x00 done\n' > $S/t12/agents/desk/instructions.md
# 13 symlinked field   14 symlink named as a kind stem   15 deep nesting
mk t13; echo 'Real text.' > $S/t13/real.md; rm $S/t13/agents/desk/instructions.md
        ln -s ../../real.md $S/t13/agents/desk/instructions.md
mk t14; ln -s ../desk $S/t14/agents/desk/loop
mk t15; rm $S/t15/agents/desk/instructions.md; P=$S/t15/agents/desk/instructions
        for i in $(seq 1 40); do P=$P/d$i; done; mkdir -p $P; echo deep > $P/x.md
# 16 / 16b symlinked self file pointing outside the workspace
mkdir -p $S/outside; printf 'name: Evil\ndescription: …\ninstructions: …\n' > $S/outside/evil.yaml
mk t16b; rm $S/t16b/agents/desk/instructions.md $S/t16b/agents/desk/agent.yaml
         ln -s $S/outside/evil.yaml $S/t16b/agents/desk/agent.yaml
# 17 whole agent folder is a symlink outside
mk t17;  mkdir -p $S/outside2/agent-out; ln -s $S/outside2/agent-out $S/t17/agents/imported
```

Headline transcripts:

```
$ $B check  t10b   →  OK — … loaded cleanly (13 settings).
$ $B discover t10b →  "id": "pact:audit",  "path": …/agents/2024-audit/agent.yaml

$ $B check  t16b   →  OK — … loaded cleanly (9 settings).
$ $B discover t16b →  "id": "pact:desk", "name": "Evil",
                      "description": "An agent definition living outside the workspace tree."

$ $B check  t7b    →  OK — … loaded cleanly (17 settings).
$ $B discover t7b  →  "id": "pact:My Desk.v2"
```

## Appendix B — files read (primary evidence)

```
filedef/prompty/spec/spec.md
filedef/dotprompt/js/src/parse.ts, js/src/stores/dir.ts, spec/{partials,metadata,picoschema}.yaml
filedef/genkit/js/ai/src/prompt.ts
filedef/promptl/src/compiler/scan.ts, src/constants.ts, src/error/errors.ts
filedef/skills-anthropic/{README.md, spec/agent-skills-spec.md, template/SKILL.md, skills/pdf/SKILL.md}
filedef/goose/crates/goose/src/skills/mod.rs, src/sources.rs,
  src/recipe/{mod,local_recipes,read_recipe_file_content,template_recipe,validate_recipe}.rs,
  crates/goose-sdk-types/src/custom_requests.rs
filedef/continue/core/config/markdown/loadMarkdownSkills.ts, core/config/loadLocalAssistants.ts,
  packages/config-yaml/src/load/{merge,unroll,blockDuplicationDetector}.ts,
  packages/config-yaml/src/markdown/{markdownToRule,getRuleType,agentFiles}.ts
filedef/aider/aider/main.py, aider/args.py
filedef/opencode/packages/opencode/src/config/{paths,entry-name,markdown,agent,parse,config}.ts,
  src/skill/discovery.ts, packages/core/src/v1/config/agent.ts
filedef/cline/apps/vscode/src/core/context/instructions/user-instructions/{skills,frontmatter}.ts,
  apps/vscode/src/core/storage/skill-directories.ts
filedef/roo-code/src/core/prompts/sections/custom-instructions.ts,
  packages/types/src/{mode,roomodes-schema}.ts
protocols/agents-md/{AGENTS.md, README.md, components/HowToUseSection.tsx}
protocols/oci-image-spec/{considerations.md, descriptor.md}
frameworks/vercel-eve/packages/eve/src/discover/{filesystem,grammar,named-source-directory}.ts
frameworks2/dify/api/services/{app_dsl_service.py, dsl_version.py}, api/constants/dsl_version.py
frameworks2/langflow/src/backend/base/langflow/initial_setup/setup.py
config/cue/doc/ref/spec.md
config/pkl/docs/modules/language-reference/pages/index.adoc
eval/phoenix/kustomize/{base,auth}/kustomization.yaml
routing/litellm/helm/litellm-helm/Chart.yaml
~/.cargo/registry/.../serde_yaml-0.9.34+deprecated/src/{de,mapping}.rs
gaia-ai-runtime/bud-agentic-runtime/sdk-and-declarative-dev.md (§Manifest-First, lines 341-420)
```

### Appendix B-bis — **[v2]** files read for the new sections

```
filedef/nextjs-app-router/packages/next/src/
  build/validate-app-paths.ts                  (whole file, 281 lines)
  build/route-discovery.ts                     (1-140)
  build/file-classifier.ts                     (whole file, 70 lines)
  build/webpack/loaders/next-app-loader/index.ts (75-120, 300-400, 695-698)
  build/utils.ts                               (1471-1479, isReservedPage)
  lib/recursive-readdir.ts                     (whole file)
  server/lib/find-page-file.ts                 (1-170)
  shared/lib/segment.ts                        (1-60)
  shared/lib/router/utils/app-paths.ts         (whole file, 82 lines)
  shared/lib/page-path/get-page-paths.ts       (whole file)
  server/route-matcher-managers/dev-route-matcher-manager.ts (85-135)
config/kubevela/e2e/addon/mock/testdata/fluxcd/resources/crds/bucket.yaml (138-146)
config/kubevela/charts/vela-core/templates/defwithtemplate/{command,configmap,pvc}.yaml
filedef/skills-anthropic/spec/agent-skills-spec.md      (re-checked: still a 3-line redirect)
frameworks2/dify/api/constants/dsl_version.py           (re-checked: still 0.7.0)

agent-inter-op (this repo, @ master 2026-08-07):
  crates/pact-loader/src/lib.rs                (1-140, 600-1000, 1100-1340)
  crates/pact-loader/src/policy.rs             (250-420, 440-520)
  crates/pact-cli/tests/the_workspace_a_check_finds_is_the_workspace_a_runtime_finds.rs (400-500)
  target/debug/pact                            (executed, §5A / Appendix A-bis)
```
