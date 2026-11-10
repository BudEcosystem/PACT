#!/usr/bin/env python3
"""Every PACT keyword, and the primitives it is built from.

The evidence behind docs/97-PRIMITIVES.md section 6 and Appendix A. It loads
spec/schema.yaml, assigns every field of every group to one or more of the seven
primitives (main ingredient first), and refuses to finish if a group in the
schema has no entry here or a group here is not in the schema - so a keyword
added to the schema without a decision about what it is made of fails this
script rather than going uncounted.

    python3 scripts/primitive-coverage.py            # counts
    python3 scripts/primitive-coverage.py --table    # one row per keyword
    python3 scripts/primitive-coverage.py --choices  # one row per closed choice

The schema also closes 75 of its fields over a fixed list of words (322 words in
all: the eleven things a stage can do, the eight things a limit may do when it
runs out, and so on). Each word is a feature of its own, so each is mapped too.
A word inherits its field's primitives unless CH below says otherwise.

"-" means the keyword has no behaviour: words written for a person (a
description, a because, a name). "Flow" includes handlers and triggers, which
is where hooks, interceptors, policies, ports and failure plans live.
"""
import yaml, sys, collections
S,ST,A,F,C,H,AL,N = "Shape","Store","Actor","Flow","Check","Flow","Allowance","-"
L="Origin"
# group default, then field overrides. Each value: list of primitives (first = primary)
G = {
 "workspace": ([F], {"detectors":[C,S],"name":[N],"pact-version":[ST],"workspace-id":[ST],"description":[N],"owner":[A],
    "profile":[ST],"durability":[ST],"allow-egress":[AL,L],"agents":[A,F],"workflows":[F,A],"shapes":[S],
    "template-language":[S,L],"time-zone":[S],"calendar":[ST],"remembers":[ST],"owners":[AL,A],"release":[H,A,C],
    "tools":[A],"resources":[A],"knowledge":[ST],"skills":[ST],"programs":[A],"values":[ST],"policies":[H,C,A],
    "redaction":[H,L,C],"questions":[A,S],"evals":[F,C],"learning":[F,H,AL],"ports":[H],"loops":[F],
    "context-policies":[H,ST],"bundles":[ST,AL],"interceptors":[H,AL],"watch":[H,ST],"models":[ST,A]}),
 "agent": ([A], {"name":[N],"description":[N],"base":[ST],"instructions":[A],"team":[A,F],"teamwork":[F,AL],
    "uses":[AL],"accepts":[S],"answers-with":[S],"answers-with-mode":[S,A],"checked-by":[C,F],"checks-at-most":[AL,F],
    "run-inputs":[S,ST],"needs":[C,A],"limits":[AL],"settings":[A],"policy":[H],"evals":[C,F],"model":[A],
    "model-for-checking":[A],"loop":[F],"variants":[F,C],"context-policy":[H,ST],"remembers":[ST],
    "interceptors":[H],"voice":[F,A,H],"turns":[ST]}),
 "variant": ([F], {"when":[N],"instructions":[A],"says":[A],"steps-at-most":[AL],"may-use":[AL],"turns":[ST]}),
 "voice": ([A], {"pipeline":[F,A],"talking":[H],"hears-with":[A],"speaks-with":[A],"speaks-as":[A],
    "languages":[S,C],"turn-ends-after":[H],"may-be-interrupted":[H],"keeps-the-audio":[ST,L]}),
 "turn": ([ST], {"from":[L,ST],"says":[ST],"attaches":[ST,S],"calls":[ST,A],"with":[ST],"answer":[ST]}),
 "value": ([ST], {"description":[N],"shape":[S],"rows-are":[S],"value":[ST,S]}),
 "program": ([A], {"description":[N],"engine":[A],"determinism":[A],"takes":[S],"answers-with":[S],
    "fuel":[AL],"body":[A,ST]}),
 "program-fuel": ([AL], {"when-it-runs-out":[H,AL]}),
 "catalog": ([ST], {"version":[ST,A],"default":[A],"models":[ST,A],"benchmarks":[ST]}),
 "benchmark": ([ST], {"description":[N],"runs":[A],"with":[A]}),
 "model": ([A], {"description":[N],"family":[ST],"tier":[ST],"also-known-as":[ST],"served-by":[A,AL],
    "capabilities":[A],"reasoning":[ST],"cost":[ST,AL],"kind":[A],"benchmarks":[ST],"speed":[ST]}),
 "served-by": ([A], {"endpoint":[A,AL],"region":[AL,ST]}),
 "model-can": ([A], {"modality-in":[S,A],"modality-out":[S,A],"languages":[S,A],"dimensions":[S,A],
    "context-window":[ST,A]}),
 "model-speed": ([ST], {}), "figure": ([ST], {}), "provenance": ([ST], {}), "model-cost": ([ST], {}),
 "needs": ([C], {"prefer":[C,F],"because":[N]}),
 "limits": ([AL], {"unbounded":[AL,A],"cost-per-request-from":[AL,ST],"feel":[C],"starts-from":[AL,H],"paused-during":[AL,F],"milestones":[H],
    "when-it-runs-out":[H,AL],"asks":[A],"measured-at":[C],"counted-per":[AL,ST],"resets-every":[AL,H]}),
 "settings": ([A], {}),
 "resource": ([A], {"available-when":[AL,C],"auth":[AL],"engines":[A],"asks-to-run":[H,A],
    "asks-to-connect":[H,A],"tool-snapshot-digest":[ST,C],"tool-snapshot-taken-at":[ST],
    "tool-snapshot-max-age":[C,AL],"published":[ST],"if-it-changes":[H,C],"asks-when-it-changes":[A],"description":[N]}),
 "knowledge": ([ST], {"description":[N],"looked-up-by":[ST],"split-by":[ST],"passages-at-most":[AL,ST],
    "must-cite":[C],"use-when":[A],"do-not-use-when":[A],"if-unsure":[A],"embedded-by":[A],"reranked-by":[A],
    "interface":[A],"chosen-by":[A,C],"implements":[A]}),
 "skill": ([ST], {"available-when":[AL,C],"name":[N],"description":[A],"use-when":[A],"do-not-use-when":[A],
    "if-unsure":[A],"costs-about":[AL],"content":[ST],"references":[ST],"scripts":[ST],"assets":[ST],
    "interface":[A],"chosen-by":[A,C],"implements":[A]}),
 "published": ([ST], {"instructions":[L,ST]}), "published-tool": ([ST], {"takes":[S],"answers-with":[S]}),
 "credential-reference": ([AL], {}),
 "tool": ([A], {"carries":[L,C],"rests-after":[AL,C],"rests-for":[AL],"available-when":[AL,C],"description":[A],"connect":[A],"url":[A,AL],"method":[A],"says":[A],
    "actions":[A,AL],"category":[N],"interface":[A],"chosen-by":[A,C],"implements":[A],"schemas-from":[S,ST],
    "unlisted-actions":[AL,H]}),
 "action": ([A], {"claim-lasts":[ST,AL],"gets-hidden-values":[L,AL],"writes":[A,ST],"description":[A],"takes":[S],"answers-with":[S],"program":[A],"reads-only":[A],
    "needs-a-person":[H,A],"spends-money":[A,ST],"same-request-key":[ST],"same-request-key-across":[ST],
    "bind":[F,ST],"projects-with":[H,A],"remember-as":[ST],"inspects":[AL,C],"undone-by":[A,F],
    "status-check":[A,F],"calls":[A],"passes":[A]}),
 "policy": ([H], {"applies-to":[AL],"ask-a-person":[H,C,A]}),
 "question-rule": ([H], {"when":[C],"because":[N],"question":[A],"first-times":[AL,ST]}),
 "when-this": ([C], {"effect":[C,A],"in-share":[C,S],"looks-like":[C,S],"tool":[C,H]}), "comparand": ([C], {}),
 "question": ([A], {"description":[N],"says":[A],"answer":[S],"shows":[L,A],"asked-of":[A],
    "answer-within":[AL,H],"answered-by":[F],"enough-is":[F,C],"asked-in":[A],"urgency":[A],
    "not-the-same-as":[C,A],"needs-signature":[A,C],"starts-with":[ST],"ordered-by":[F],
    "counts-events-from":[H],"only-when":[H,C],"reminds-at":[H],"if-nobody-answers":[H,F],
    "escalates-to":[A,F],"checked-by":[C,A]}),
 "reminder": ([H], {"tells":[A],"hands-over-to":[A,F],"runs":[F]}),
 "evals": ([F], {"description":[N],"population":[ST,L],"from-the-last":[ST],"sample":[F],"reviewed-by":[A],
    "sliced-by":[C],"runs-every":[H],"must-pass":[C],"rules":[C],"metrics":[A,C],"graded-by":[A],"cases":[ST]}),
 "eval-rule": ([C], {"judged":[A,C],"program":[A,C],"library":[C],"because":[N]}),
 "metric": ([A], {"threshold":[C],"name":[N]}),
 "call-order": ([C], {}),
 "case": ([ST], {"when":[ST],"expect":[ST,C],"because":[N],"must-also":[C],"split":[ST,L,AL]}),
 "learning": ([F], {"enabled":[AL],"may-improve-on-its-own":[AL],"needs-a-person-to-approve":[AL,H],
    "keep-only-if":[C],"review":[H],"cycle-limits":[AL],"models":[A],"drift":[C,AL]}),
 "learning-model": ([A], {"role":[A,AL]}),
 "cycle-limits": ([AL], {}), "drift": ([C], {"at-most":[C,ST]}),
 "port": ([H], {"description":[N],"kind":[H],"every":[H],"says":[A],"if-still-running":[H,ST,F],
    "through":[A],"answers":[A,F],"accepts":[S],"bind":[F,ST],"only-when":[C,H],"signed-with":[C,AL],
    "in-time-zone":[S],"if-missed":[H],"per-row-of":[F,ST],"answer-within":[AL],
    "same-conversation-when":[ST],"counts-as-the-same-for":[ST,C],"ordered-by":[F],"undo":[F],
    "then-run":[F],"who-can-reach-it":[AL],"remembers":[ST]}),
 "workflow": ([F], {"description":[N],"base":[ST],"accepts":[S],"answers-with":[S],"questions":[A,S],
    "policy":[H],"limits":[AL],"evals":[C,F],"remembers":[ST],"hides":[L,AL],"data-stays-in":[L,AL,ST],
    "kept-for":[ST],"undone-by":[F,A],"published-as":[A,H],"release":[H,A,C]}),
 "moment": ([S], {"at":[ST],"counted-in":[S,ST]}),
 "ownership": ([AL], {"owned-by":[AL,A],"locked-until":[AL,S]}),
 "release": ([H], {"asks":[A]}),
 "loop": ([F], {"description":[N],"based-on":[ST]}),
 "stage": ([F], {"forks":[ST,F],"keeps-taking":[F,ST],"stops":[F],"does":[F,A],"says":[A],"asks":[A],"may-use":[AL],"at-most":[AL],"fuel":[AL],"runs-in":[A],
    "call":[F,A],"may-call":[AL],"bind":[F,ST],"version":[ST,A],"chooses-between":[F,C],"by":[F,C,A],
    "over":[F,ST],"identified-by":[ST],"combines-by":[ST],"teamwork":[F,AL],"until":[C],"remembers":[ST],
    "checked-by":[C],"checks-at-most":[AL],"undone-by":[F,A],"limits":[AL],"if-it-fails":[H,F]}),
 "rung": ([F], {"rules":[C],"agent":[A],"if-unsure-below":[C],"if-it-disagrees":[F,C],"asks":[A]}),
 "route-rule": ([C], {"choose":[F],"because":[N]}),
 "if-it-fails": ([H], {"after-that":[H,F],"gives-up-after":[AL],"backup":[A,F],"carry-on-with":[ST],
    "asks":[A],"new-version-of":[H,ST],"undo":[F],"undo-where":[C]}),
 "outcome": ([F], {"heard":[H,F],"decided-by":[A,F],"may-go-to":[AL,F]}),
 "context-policy": ([H], {"description":[N],"when-full":[H,C,ST],"always-keep":[ST,L],"then":[F,ST],
    "summarised-by":[A],"if-it-still-does-not-fit":[H,F],"asks":[A]}),
 "tidy-step": ([ST], {"what":[ST,A],"applies-to":[ST,L],"down-to":[ST,AL]}),
 "interceptor": ([H], {"description":[N],"applies-to":[AL],"runs-at":[H],"may":[AL],"rules":[H,C]}),
 "redaction": ([L], {"description":[N],"hide":[L,C,F]}),
 "detector": ([C], {"description":[N],"looks-like":[C,S],"examples":[C,N]}),
 "watch": ([H], {"description":[N],"writes-to":[ST,L]}),
 "state": ([ST], {"shared-with":[ST,AL],"admitted-when":[ST,C],"admitted-by":[ST,C,A],"description":[N],"shaped-like":[S],"never-from":[L,AL],"kept-per":[ST],"comes-from":[ST,F],
    "stops-being-true-when":[ST,H]}),
 "bundle": ([ST], {"description":[N],"brings":[AL],"from":[ST]}),
 "teamwork": ([F], {"may-start":[AL,A],"divides-the-budget":[AL],"shares":[AL],"gives-up-after":[AL,F],
    "if-someone-fails":[H,F],"asks":[A],"enough-is":[F,C]}),
}
# (group.field) -> {choice: primitives}. Only where a word is made of something
# other than its field. A stage that `decide`s is a Flow choose over a Check; one
# that `run-code`s is a program Actor under a fuel Allowance.
CH = {
 "stage.does": {"stop":[F],"think":[A,F],"use-tools":[A,AL,F],"check-its-work":[C,A,F],"ask-someone":[A,F],
    "answer":[F],"run-code":[A,AL,F],"call":[F,A],"decide":[F,C],"each":[F,ST],"repeat":[F,AL,C],"together":[F,ST]},
 "limits.when-it-runs-out": {"stop-and-say-so":[H],"ask-a-person":[H,A],"answer-with-what-it-has":[H,F],
    "use-a-backup":[H,A],"carry-on":[H,ST],"wait-for-a-new-version":[H,ST],"undo":[H,A],"wait-its-turn":[H,AL]},
 "if-it-fails.after-that": {"stop-and-say-so":[H],"ask-a-person":[H,A],"use-a-backup":[H,A],"carry-on":[H,ST],
    "wait-for-a-new-version":[H,ST],"undo":[H,A]},
 "program-fuel.when-it-runs-out": {"stop-and-say-so":[H],"ask-a-person":[H,A],"answer-with-what-it-has":[H,F]},
 "interceptor.may": {"hide-values":[L,H],"stop-the-run":[H],"send-elsewhere":[H,A,AL],"change-the-answer":[H,S],"change-the-request":[H,S]},
 "teamwork.waits-for": {"everyone":[F],"anyone":[F],"enough-of-them":[F,C],"the-first-good-answer":[F,C],"whoever-answers-in-time":[F,AL]},
 "teamwork.if-someone-fails": {"carry-on":[H,F],"stop-the-others":[H,F],"ask-a-person":[H,A]},
 "teamwork.may-start": {"catalogue":[AL,ST],"narrowed-new":[AL,A]},
 "port.if-still-running": {"start":[H],"queue":[H,ST],"join":[H,ST],"cancel-previous":[H,F],"skip":[H,C],"stop":[H]},
 "port.kind": {"conversation":[H,ST],"schedule":[H,ST],"inbound-call":[H,A],"event":[H,ST]},
 "question.answered-by": {"anyone":[F],"everyone":[F],"enough-of-them":[F,C]},
 "question.if-nobody-answers": {"decline":[H,F],"escalate":[H,A],"stop-and-say-so":[H]},
 "tidy-step.what": {"shorten-long-results":[ST,A],"drop-parts":[ST,L],"summarise-older":[ST,A],"keep-recent-only":[ST]},
 "context-policy.if-it-still-does-not-fit": {"use-it-anyway":[H],"ask-a-person":[H,A],"stop":[H]},
 "resource.if-it-changes": {"stop-and-say-so":[H],"ask-a-person":[H,A],"use-what-was-reviewed":[H,ST],"use-the-new-one":[H,ST]},
 "learning.enabled": {"False":[AL],"propose-only":[AL,H],"applies-safe-changes-itself":[AL,ST]},
 "learning.keep-only-if": {"a-person-approves-it":[C,A],"scores-higher-on-evals":[C,F]},
 "evals.population": {"authored-enumeration":[ST],"promoted-traces":[ST,C],"sampled-frame":[ST,C],"past-runs":[ST]},
 "workflow.published-as": {"tool":[A,S],"mcp-tool":[A,S],"a2a-agent":[A,H],"api":[A,H]},
 "needs.prefer": {"cheapest":[C,ST],"fastest":[C,ST],"best-on-the-evals":[C,F]},
 "knowledge.looked-up-by": {"meaning":[ST,A],"words":[ST],"meaning-and-words":[ST,A]},
 "voice.pipeline": {"pact-picks":[F,C],"transcribe-think-speak":[F,A],"one-speech-model":[F,A]},
 "when-this.effect": {"reads":[C,A],"writes":[C,A],"spends":[C,A,AL],"cannot-be-undone":[C,A]},
 "tool.carries": {"private-data":[L],"untrusted-content":[L],"a-way-out":[L,AL]},
 "state.shared-with": {"this-agent":[ST],"the-team":[ST,AL]},
 "rung.if-it-disagrees": {"keep-its-answer":[F],"go-on":[F,C]},
}
d=yaml.safe_load(open('spec/schema.yaml'))['groups']
missing=[g for g in d if g not in G]; extra=[g for g in G if g not in d]
assert not missing and not extra, (missing, extra)
prim=collections.Counter(); first=collections.Counter(); rows=[]
for g,gv in d.items():
    dflt,ov=G[g]
    for k in (gv.get('fields') or {}):
        ps=ov.get(k,dflt); rows.append((g,k,ps)); first[ps[0]]+=1
        for p in dict.fromkeys(ps): prim[p]+=1
bad=[r for r in rows if not r[2]]
print("keywords mapped:",len(rows),"unmapped:",len(bad))
print("primary primitive counts:",dict(first.most_common()))
print("touching counts:",dict(prim.most_common()))
if "--table" in sys.argv:
    for g,k,ps in rows: print(f"| `{g}.{k}` | {' + '.join(dict.fromkeys(ps))} |")
# every closed choice, mapped
badch=[k for k in CH if k.split(".")[0] not in d or k.split(".")[1] not in (d[k.split(".")[0]].get('fields') or {})]
assert not badch, badch
crows=[]; cfirst=collections.Counter()
for g,gv in d.items():
    for k,fv in (gv.get('fields') or {}).items():
        for c in (fv.get('choices') or []):
            ov=CH.get(f"{g}.{k}",{}); ps=ov.get(str(c), G[g][1].get(k,G[g][0]))
            crows.append((g,k,str(c),ps)); cfirst[ps[0]]+=1
stale=[(f,c) for f,ov in CH.items() for c in ov if str(c) not in [str(x) for x in (d[f.split(".")[0]]['fields'][f.split(".")[1]].get('choices') or [])]]
assert not stale, stale
print("closed choices mapped:",len(crows),"primary primitive counts:",dict(cfirst.most_common()))
if "--choices" in sys.argv:
    for g,k,c,ps in crows: print(f"| `{g}.{k}: {c}` | {' + '.join(dict.fromkeys(ps))} |")
