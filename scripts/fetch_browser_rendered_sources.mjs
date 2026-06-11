import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdir, readFile, writeFile } from "node:fs/promises";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const DEFAULT_QUEUE = join(ROOT, "data", "mvp", "browser_render_queue.csv");
const DEFAULT_CSV_OUT = join(ROOT, "data", "extraction", "browser_rendered_sources.csv");
const DEFAULT_JSON_OUT = join(ROOT, "data", "extraction", "browser_rendered_sources.json");
const DEFAULT_TEXT_DIR = join(ROOT, "data", "extraction", "rendered_source_texts");
const MIN_TEXT_LENGTH = 500;

function parseArgs(argv) {
  const args = {
    queue: DEFAULT_QUEUE,
    csvOut: DEFAULT_CSV_OUT,
    jsonOut: DEFAULT_JSON_OUT,
    limit: undefined,
    timeoutMs: 30000,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === "--queue") args.queue = next;
    if (arg === "--csv-out") args.csvOut = next;
    if (arg === "--json-out") args.jsonOut = next;
    if (arg === "--limit") args.limit = Number.parseInt(next, 10);
    if (arg === "--timeout-ms") args.timeoutMs = Number.parseInt(next, 10);
    if (arg.startsWith("--")) index += 1;
  }
  return args;
}

function parseCsv(text) {
  const rows = [];
  let field = "";
  let row = [];
  let quoted = false;
  const pushField = () => {
    row.push(field);
    field = "";
  };
  const pushRow = () => {
    if (row.length === 1 && row[0] === "") return;
    rows.push(row);
    row = [];
  };

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      pushField();
    } else if (char === "\n") {
      pushField();
      pushRow();
    } else if (char !== "\r") {
      field += char;
    }
  }
  pushField();
  pushRow();

  const [headers, ...dataRows] = rows;
  if (!headers) return [];
  return dataRows.map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])),
  );
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

async function writeOutputs(rows, csvOut, jsonOut) {
  const fieldnames = [
    "rank",
    "mvp_scope",
    "brand",
    "model",
    "registrations_ytd",
    "source_url",
    "final_url",
    "http_status",
    "source_domain",
    "render_status",
    "render_error",
    "source_hash",
    "source_text_path",
    "source_text_length",
    "source_text_preview",
    "fetched_at",
    "extraction_status",
    "notes",
  ];
  const csv = [
    fieldnames.join(","),
    ...rows.map((row) => fieldnames.map((field) => csvEscape(row[field])).join(",")),
  ].join("\n") + "\n";
  await mkdir(dirname(csvOut), { recursive: true });
  await mkdir(dirname(jsonOut), { recursive: true });
  await writeFile(csvOut, csv, "utf8");
  await writeFile(jsonOut, `${JSON.stringify(rows, null, 2)}\n`, "utf8");
}

function mergeRenderedRows(existingRows, newRows) {
  const rows = new Map();
  for (const row of existingRows) {
    if (row.source_url) rows.set(row.source_url, row);
  }
  for (const row of newRows) {
    if (row.source_url) rows.set(row.source_url, row);
  }
  return [...rows.values()].sort((a, b) => Number(a.rank || 999) - Number(b.rank || 999));
}

function loadPlaywright() {
  const attempts = [
    createRequire(import.meta.url),
    createRequire(join(homedir(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules", "playwright", "package.json")),
  ];
  const errors = [];
  for (const requireFrom of attempts) {
    try {
      return requireFrom("playwright");
    } catch (error) {
      errors.push(error.message);
    }
  }
  throw new Error(`Playwright was not found. ${errors.join(" | ")}`);
}

function cleanText(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function sourceDomain(url) {
  try {
    return new URL(url).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return "";
  }
}

function blockedRow(row, status, error) {
  return {
    rank: row.rank ?? "",
    mvp_scope: row.mvp_scope ?? "",
    brand: row.brand ?? "",
    model: row.model ?? "",
    registrations_ytd: row.registrations_ytd ?? "",
    source_url: row.source_url ?? "",
    final_url: "",
    http_status: "",
    source_domain: sourceDomain(row.source_url),
    render_status: status,
    render_error: error,
    source_hash: "",
    source_text_path: "",
    source_text_length: 0,
    source_text_preview: "",
    fetched_at: new Date().toISOString(),
    extraction_status: "blocked",
    notes: "No public data is populated from this row until rendered official source text is captured and validated.",
  };
}

function slug(value) {
  return String(value ?? "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

async function renderRow(playwright, browser, row, timeoutMs) {
  const page = await browser.newPage({
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SwedishEVAdvisor/0.1",
    locale: "sv-SE",
  });
  try {
    const response = await page.goto(row.source_url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    await page.waitForLoadState("networkidle", { timeout: Math.min(timeoutMs, 12000) }).catch(() => {});
    const text = cleanText(await page.evaluate(() => document.body?.innerText ?? ""));
    const sourceHash = createHash("sha256").update(text, "utf8").digest("hex");
    const httpStatus = response?.status() ?? "";
    const pageNotFound =
      Number(httpStatus) >= 400 ||
      /sidan kunde inte hittas|page not found|404|not found/i.test(text.slice(0, 1200));
    const renderStatus = pageNotFound
      ? "rendered_page_not_found"
      : text.length >= MIN_TEXT_LENGTH
        ? "rendered_source_ready"
        : "rendered_text_too_short";
    let sourceTextPath = "";
    if (renderStatus === "rendered_source_ready") {
      await mkdir(DEFAULT_TEXT_DIR, { recursive: true });
      sourceTextPath = join(
        DEFAULT_TEXT_DIR,
        `${String(row.rank ?? "").padStart(2, "0")}-${slug(row.brand)}-${slug(row.model)}-${sourceHash.slice(0, 10)}.txt`,
      );
      await writeFile(sourceTextPath, `${text}\n`, "utf8");
    }
    return {
      rank: row.rank ?? "",
      mvp_scope: row.mvp_scope ?? "",
      brand: row.brand ?? "",
      model: row.model ?? "",
      registrations_ytd: row.registrations_ytd ?? "",
      source_url: row.source_url ?? "",
      final_url: page.url(),
      http_status: httpStatus,
      source_domain: sourceDomain(page.url()),
      render_status: renderStatus,
      render_error: renderStatus === "rendered_source_ready" ? "" : renderStatus.replace("rendered_", ""),
      source_hash: renderStatus === "rendered_source_ready" ? sourceHash : "",
      source_text_path: sourceTextPath,
      source_text_length: text.length,
      source_text_preview: text.slice(0, 500),
      fetched_at: new Date().toISOString(),
      extraction_status: renderStatus === "rendered_source_ready" ? "queued" : "blocked",
      notes: "Rendered official source text captured for AI extraction staging.",
    };
  } catch (error) {
    return blockedRow(row, "render_failed", error.message);
  } finally {
    await page.close().catch(() => {});
    void playwright;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const queueText = await readFile(args.queue, "utf8");
  let rows = parseCsv(queueText)
    .filter((row) => row.queue_status === "queued")
    .sort((a, b) => Number(a.priority || a.rank || 999) - Number(b.priority || b.rank || 999));
  if (Number.isFinite(args.limit)) rows = rows.slice(0, args.limit);

  const playwright = loadPlaywright();
  const launchAttempts = [
    { headless: true, channel: "msedge" },
    { headless: true, channel: "chrome" },
    { headless: true },
  ];
  let browser;
  const launchErrors = [];
  for (const options of launchAttempts) {
    try {
      browser = await playwright.chromium.launch(options);
      break;
    } catch (error) {
      launchErrors.push(`${options.channel ?? "bundled"}: ${error.message.split("\n")[0]}`);
    }
  }
  if (!browser) {
    throw new Error(`No browser runtime could be launched. ${launchErrors.join(" | ")}`);
  }
  const rendered = [];
  try {
    for (const row of rows) {
      rendered.push(await renderRow(playwright, browser, row, args.timeoutMs));
    }
  } finally {
    await browser.close().catch(() => {});
  }

  let existing = [];
  try {
    existing = parseCsv(await readFile(args.csvOut, "utf8"));
  } catch {}
  const merged = mergeRenderedRows(existing, rendered);

  await writeOutputs(merged, args.csvOut, args.jsonOut);
  const ready = rendered.filter((row) => row.render_status === "rendered_source_ready").length;
  const totalReady = merged.filter((row) => row.render_status === "rendered_source_ready").length;
  console.log(`Browser-render rows processed: ${rendered.length}`);
  console.log(`Rendered sources ready: ${ready}`);
  console.log(`Rendered sources ready total: ${totalReady}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
