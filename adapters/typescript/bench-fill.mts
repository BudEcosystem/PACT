// How long one fill takes in this process, against the budget of
// `docs` §6.4 of BMH's plan (p95 ≤ 2 ms): the Jinja desk of
// `tests/trees/a-desk-that-listens-reads-and-chooses` and a long holes text,
// each filled `ROUNDS` times after a warm-up, timed one call at a time.
//
//     node --experimental-strip-types bench-fill.mts <pact_fill_wasm.wasm>
import { readFileSync } from "node:fs";
import { Filler } from "./src/fill.ts";

const ROUNDS = 2000;
const started = performance.now();
const filler = await Filler.load(readFileSync(process.argv[2]));
const loaded = performance.now() - started;
const desk = {
  text:
    "You answer the phone for {{ run_inputs.shop_name }}.\n{% if run_inputs.tier == 'gold' %}This caller is a gold customer: offer the free returns label.{% else %}Say the returns policy.{% endif %}\nSpeak as {{ run_inputs.brand_voice }}.\n{% for note in remembers.caller_notes %}- {{ note }}\n{% endfor %}",
  language: "jinja",
  "run-inputs": { "shop-name": "Acme", tier: "gold", "brand-voice": "warm" },
  remembers: { "caller-notes": Array.from({ length: 20 }, (_, i) => `note ${i}`) },
};
const long = {
  text: Array.from({ length: 200 }, (_, i) => `Line ${i} for {{run-inputs.brand}} and {{remembers.style}}.`).join("\n"),
  language: "holes",
  "run-inputs": { brand: "Acme" },
  remembers: { style: ["short", "kind"] },
};
const quantile = (sorted: number[], q: number): number => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
const report: Record<string, unknown> = { loadMs: Number(loaded.toFixed(2)) };
for (const [name, request] of Object.entries({ desk, long })) {
  for (let i = 0; i < 200; i++) filler.fill(request);
  const times: number[] = [];
  for (let i = 0; i < ROUNDS; i++) {
    const t = performance.now();
    filler.fill(request);
    times.push(performance.now() - t);
  }
  times.sort((a, b) => a - b);
  report[name] = { p50Ms: Number(quantile(times, 0.5).toFixed(4)), p95Ms: Number(quantile(times, 0.95).toFixed(4)), p99Ms: Number(quantile(times, 0.99).toFixed(4)) };
}
process.stdout.write(`${JSON.stringify(report)}\n`);
