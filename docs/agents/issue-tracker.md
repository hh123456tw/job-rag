# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`（本專案：`.scratch/job-rag/`）
- The spec is `.scratch/job-rag/spec.md`（`SPEC.md` 的副本；以根目錄 `SPEC.md` 為準）
- Tickets are one file each at `.scratch/job-rag/issues/<NN>-<slug>.md`, numbered from `01`
- Triage state is a `Status:` line near the top of each ticket
- Comments append to the bottom under a `## Comments` heading
- A ticket is unblocked when every ticket in its `Blocked by:` line has `Status: resolved`

## Publish / fetch

Publish: create a file under `.scratch/job-rag/`. Fetch: read the file at the path or number given.
