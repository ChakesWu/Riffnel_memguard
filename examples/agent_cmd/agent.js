// Minimal agent in Node.js speaking Riffnel's --agent-cmd protocol (no Riffnel code involved).
//   riffnel-memguard ask "金卡免年费需要刷几笔？" --scope product=gold_card --at 2026-08-10 \
//       --agent-cmd "node examples/agent_cmd/agent.js .riffnel/memories.json"
// stdin : {"question": "...", "scope": {...}}      stdout (last line): {"answer": "...", "retrieved_ids": [...]}
const fs = require("fs");
const memories = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const req = JSON.parse(fs.readFileSync(0, "utf8").split("\n")[0]);

const grams = (t) => { const s = new Set(); for (let i = 0; i < t.length - 1; i++) s.add(t.slice(i, i + 2)); return s; };
const q = grams(req.question);
const fits = (m) => Object.entries(m.scope || {}).every(([k, v]) => !(k in req.scope) || req.scope[k] === v);
const ranked = memories
  .filter((m) => (m.status || "active") === "active" && fits(m))
  .map((m) => [m, [...grams(m.content)].filter((g) => q.has(g)).length])
  .sort((a, b) => b[1] - a[1]);

console.error("agent.js: ranked", ranked.length, "candidates");  // stderr is ignored on success
const top = ranked[0] && ranked[0][1] > 0 ? ranked[0][0] : null;
console.log(JSON.stringify(top ? { answer: top.content, retrieved_ids: [top.id] }
                              : { answer: "抱歉，我没有相关信息。", retrieved_ids: [] }));
