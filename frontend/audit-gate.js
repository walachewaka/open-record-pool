/*
 * npm-audit gate (MOO-89). Runs `npm audit --omit=dev --json`, collects
 * high/critical advisories, subtracts the ids accepted in audit-ignore.txt,
 * and exits non-zero (listing the rest) if any remain. Plain Node, no deps.
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

function accepted() {
  const p = path.join(__dirname, "audit-ignore.txt");
  if (!fs.existsSync(p)) return new Set();
  return new Set(
    fs
      .readFileSync(p, "utf8")
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith("#"))
  );
}

function collect(json) {
  // npm v7+ schema: { vulnerabilities: { <name>: { severity, via: [...] } } }
  const found = new Map(); // id -> {name, severity, title}
  const vulns = (json && json.vulnerabilities) || {};
  for (const name of Object.keys(vulns)) {
    const v = vulns[name];
    if (!v || !["high", "critical"].includes(v.severity)) continue;
    for (const via of v.via || []) {
      if (typeof via === "object" && via.url) {
        const id = (via.url.match(/GHSA-[\w-]+/) || [via.source || via.url])[0];
        found.set(String(id), {
          name,
          severity: v.severity,
          title: via.title || "",
        });
      }
    }
  }
  return found;
}

const res = spawnSync("npm", ["audit", "--omit=dev", "--json"], {
  cwd: __dirname,
  encoding: "utf8",
  shell: true,
  maxBuffer: 32 * 1024 * 1024,
});
let json;
try {
  json = JSON.parse(res.stdout || "{}");
} catch (e) {
  console.error("Could not parse npm audit JSON output.");
  process.exit(2);
}

const ignore = accepted();
const found = collect(json);
const remaining = [...found.entries()].filter(([id]) => !ignore.has(id));

if (remaining.length === 0) {
  console.log("npm audit: no un-accepted high/critical advisories.");
  process.exit(0);
}
console.error("npm audit: un-accepted high/critical advisories:");
for (const [id, info] of remaining) {
  console.error(`  ${id}  [${info.severity}] ${info.name} — ${info.title}`);
}
console.error(
  "Accept one only with a line in frontend/audit-ignore.txt AND a SECURITY.md triage row."
);
process.exit(1);
