import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { homedir } from "node:os";

const args = process.argv.slice(2);

if (args.length === 0) {
  console.error("Usage: node scripts/run_python.mjs <script.py> [...args]");
  process.exit(2);
}

const candidates = [
  process.env.PYTHON,
  "python",
  "python3",
  "py",
  join(homedir(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "python", "python.exe"),
].filter(Boolean);

let lastResult = null;

for (const candidate of candidates) {
  if (candidate.endsWith(".exe") && !existsSync(candidate)) {
    continue;
  }

  const version = spawnSync(candidate, ["--version"], { encoding: "utf-8", shell: false });
  if (version.error || version.status !== 0) {
    lastResult = version;
    continue;
  }

  const result = spawnSync(candidate, args, { stdio: "inherit", shell: false });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  process.exit(result.status ?? 0);
}

if (lastResult?.error) {
  console.error(lastResult.error.message);
}
console.error("No Python runtime found. Set PYTHON to a Python executable path.");
process.exit(1);
