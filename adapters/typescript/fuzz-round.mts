import { sentence } from "./src/limits.ts";
const vals: number[] = JSON.parse(process.argv[2]);
const out = vals.map((v) => {
  const s = sentence({
    ceiling: { field: "f", reads: "money", limit: v, unit: "", halted: "cost-limit" },
    at: 0, action: "stop-and-say-so",
  });
  return s.slice(s.indexOf("(0 of ") + 6, s.lastIndexOf(")"));
});
process.stdout.write(JSON.stringify(out));
