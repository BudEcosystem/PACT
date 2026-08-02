# PACT Research Stream — Filesystem / File-Based Agent & Prompt Definition Prior Art

**Stream:** `filesystem-prior-art`
**Date:** 2026-07-26
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

## 0. Executive summary — the four results that change PACT's design

1. **Vercel Eve's slot table is real, closed, and hardcoded — verified.** `AgentRootEntryKind`
   is a 17-member string-literal union and `classifyAgentRootEntry` is a chain of `name === "…"`
   comparisons (`vercel-eve/packages/eve/src/discover/filesystem.ts:36-56`, `:120-205`).
   The thesis's characterisation of Eve is accurate. **T5's premise is confirmed.**

2. **Nobody in this corpus has a general rule; everybody has an ad-hoc rule, and they
   contradict each other.** Two implementations of the *same* Agent Skills concept invert
   override precedence (goose: project-first-wins, `goose/crates/goose/src/skills/mod.rs:296-322`
   + `:460-485`; cline: remote>global>project last-wins, `cline/apps/vscode/src/core/context/instructions/user-instructions/skills.ts:211-268`).
   Two implementations of the *same* `.prompt` format disagree on how `a.b.c.prompt`
   parses (dotprompt `js/src/stores/dir.ts:149-160` → name `a.b`, variant `c`;
   genkit `js/ai/src/prompt.ts:846-850` → name `a`, variant `b`, `c` dropped).
   **This is the strongest possible argument for PACT specifying one normative loader.**

3. **The general rule exists and it is not new — it is CUE's.** A package is the
   unification of all files in a directory (`config/cue/doc/ref/spec.md:3164-3175`), and
   unification is "commutative, associative, and idempotent. As a consequence, order of
   evaluation is irrelevant" (`config/cue/doc/ref/spec.md:672-674`). That is *exactly*
   "a directory is a field", made sound by choosing a **conflict-detecting order-independent
   merge** instead of last-wins override. **T5 is sound if and only if PACT adopts
   unification-style merge for unordered fields and forbids the directory form for
   ordered fields unless order is carried in-band.**

4. **The single largest concrete risk to `AC-1.4` (byte-identical `canonical.json`) is not
   the Expansion Rule — it is YAML.** **[EMPIRICAL]** PyYAML (`yaml.safe_load`) parses
   `no: value` → `{False: 'value'}`, `on: third` collides with `yes: other` into one key,
   and `version: 1.10` → the float `1.1`. Rust's `serde_yaml` implements only YAML 1.2 core
   booleans (`serde_yaml-0.9.34/src/de.rs:932-938`), so the *same file* yields *different
   documents* in PACT's Rust core (D4) versus a Python adapter/eval provider (D4, D6).

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

---

## 7. What the normative algorithm must specify

This is the checklist for the loader section of `20-ARCHITECTURE`. Each item exists because
something in §5 breaks without it.

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
