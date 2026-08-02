# The Expansion Rule

> **A directory is a field; a field may be a directory.**

## Why

A format has to serve two people who want opposite things.

The **beginner** wants one file. Making them learn a directory layout before
they can write "be brief" is how a format loses the audience it was built for.

The **expert** wants a tree. A 40-line instruction, six tools and four eval
cases in one file is unreviewable, and the diff is unreadable.

Most formats pick one and bolt on the other later, which produces a slot
table — a fixed list of "these things may be directories" that grows a case
every release. Vercel Eve has 18 such cases, and its compiled manifest is at
v36 because every new slot bumps a monolith.

## How

Instead of a table, one rule applied totally. These two trees produce the
**identical loaded document**:

=== "One file"

    ```yaml title="agents/refund-desk/agent.yaml"
    name: Refund Desk
    instructions: Be precise. Check the policy before you answer.
    ```

=== "A tree"

    ```yaml title="agents/refund-desk/agent.yaml"
    name: Refund Desk
    ```
    ```markdown title="agents/refund-desk/instructions.md"
    Be precise. Check the policy before you answer.
    ```

The loader does not know that `instructions` is special. It knows that a name
on disk beside a document is a field of that document, and the schema knows what
shape that field should take when it arrives.

## What this buys

**A new field costs nothing.** Add `remembers:` to the schema and it has its
directory form the same day — `agents/x/remembers/budget.yaml` — with no loader
change. That is what makes the format extensible without touching the core.

**Nobody memorises a layout.** You put the thing where it feels natural. If it
is somewhere the loader does not expect, the diagnostic tells you where it goes.

**The digest is the same either way.** A tree written flat and the same tree
written expanded produce the same content digest, which is what makes "did this
agent change?" answerable across a refactor that only moved files.

!!! warning "One honest limit"
    Package-shaped kinds — a skill with `references/`, `assets/` and `scripts/`
    beside it — need one word in the loader's list of kind stems. Adding the
    `watch` kind cost one word, `"watch"` in `Policy::kind_stems`.

    The claim is therefore **"one word, the same one every kind costs"**, not
    "no code change ever". Eve's equivalent is a slot in a compiled manifest at
    v36 with a fixed `if`-chain, so the comparison still holds — but the earlier
    wording of this claim was wrong and was corrected after a reviewer checked
    it against the code.
