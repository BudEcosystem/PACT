# Voice, documents and embeddings

## The contract was already writable

An agent people talk to says so in what it takes and gives:

```yaml
accepts: {message: audio}
answers-with: {reply: audio}
limits: {feel: voice}
```

`documents` (a PDF, a scanned form — something a model **reads**) and `video`
are shapes beside `images`, `audio` and `file`.

## How it listens and speaks

```yaml title="agents/front-desk/agent.yaml"
voice:
  pipeline: transcribe-think-speak   # or one-speech-model, or leave it to PACT
  talking: takes-turns               # or both-at-once: the caller may interrupt
  hears-with: whisper-large-v3
  speaks-with: kokoro-82m
  speaks-as: af_heart                # checked against that model's own voices
  languages: [en-GB]
  turn-ends-after: 700ms
  keeps-the-audio: no                # a recording is personal data
```

Each named model must be the right **kind** — a transcriber where one is heard, a
speaker where one speaks — and the catalogue's voices and languages are checked.
A transcriber and a speaker on your own machine keep the caller's voice there: a
hosted language model behind them is sent words, so `allow-egress: [llm]` is the
whole grant.

## Embeddings belong to the documents

```yaml title="knowledge/handbook/handbook.yaml"
looked-up-by: meaning
embedded-by: nomic-embed-text
reranked-by: bge-reranker-v2-m3
```

The documents carry their embedder, not the agent: a question has to be turned
into numbers by the same model the documents were, or what comes back is
confidently unrelated. A local embedder makes meaning search work with nothing
allowed out of the box.
