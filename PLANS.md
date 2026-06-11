# PLANS.md

Execution template for each implementation phase.

Use this template before and during every phase. Do not jump straight to features.

## Phase Execution Template

### 1. Inspect Relevant Files

Read the smallest useful set of files before changing code.

Typical files:
- `AGENTS.md`
- `ROADMAP.md`
- `database/schema.sql`
- `database/migrations/*`
- `scripts/*`
- `src/*`
- `tests/*`
- `.env.example`
- relevant generated data under `data/`

Output:
- Files inspected.
- Existing behavior discovered.

### 2. State Current Status

Briefly describe what is already implemented and what is only mocked, local, generated, or missing.

Must identify:
- Whether Supabase/Postgres is the canonical source for this slice.
- Whether the public UI reads only canonical validated views.
- Whether Mobility Sweden is being used only for market discovery.
- Whether the current slice targets MVP top 20-30 coverage or full-market expansion.
- Whether manufacturer/importer sources are official Swedish sources.
- Whether AI output is staged, validated, published, or quarantined.

### 3. Identify Missing Pieces

List only the missing pieces relevant to the current phase.

Classify each missing piece as:
- `blocker`
- `required`
- `nice-to-have`
- `defer`

### 4. Implement The Smallest Useful Slice

Pick the smallest implementation that moves the phase toward its exit criteria.

Rules:
- Do not add unrelated product features.
- Prefer top 20-30 model coverage for MVP work unless the phase explicitly concerns full-market expansion.
- Prefer deterministic pipeline logic over manual workflows.
- Keep AI output in staging until validation passes.
- Keep public data reads restricted to canonical validated records.
- Preserve quarantine paths for uncertain or conflicting data.

### 5. Run Tests And Build

Run the checks relevant to the changed slice.

Default checks:
- Python compile for changed scripts.
- Unit tests under `tests/`.
- Frontend build for UI changes.
- Data generation script smoke tests when applicable.

If a check cannot run:
- Say exactly why.
- State the risk.
- Recommend the next verification step.

### 6. Report Results

Every phase report must include:

Changed files:
- List the exact files changed.

What works:
- Describe verified behavior.

What remains:
- Describe unfinished work and known limitations.

Next recommended task:
- One concrete next task that advances the roadmap.

## Phase Report Format

```text
Phase: <number and name>

Inspected:
- <file>

Current status:
- <status>

Missing pieces:
- [blocker|required|nice-to-have|defer] <item>

Implemented:
- <smallest useful slice>

Checks:
- <command/result>

Changed files:
- <file>

What works:
- <verified behavior>

What remains:
- <remaining work>

Next recommended task:
- <one task>
```
