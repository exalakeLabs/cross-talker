import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the Cross Talker interaction ledger", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Cross Talker — Interaction Ledger<\/title>/i);
  assert.match(html, /Cross Talker/);
  assert.match(html, /Interaction ledger/);
  assert.match(html, /Model runs/);
  assert.match(html, /Loading interactions/);
  assert.match(html, /New cross-talk/);
});

test("keeps conclusion synthesis visible and auditable", async () => {
  const [page, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);

  assert.match(page, /item\.kind === "conclusion"/);
  assert.match(page, /Synthesized conclusion/);
  assert.match(page, /What the models concluded/);
  assert.match(page, /Inspect synthesis inputs/);
  assert.match(page, /Export training record \(\.jsonl\)/);
  assert.match(page, /cross-talker\.training\.v1/);
  assert.match(page, /application\/x-ndjson/);
  assert.match(page, /final_responses: finalResponses/);
  assert.match(page, /Responses provided to the engine/);
  assert.match(page, /item\.kind !== "conclusion"/);
  assert.match(css, /\.conclusion-panel/);
  assert.match(css, /\.conclusion-heading/);
  assert.match(css, /\.export-conclusion/);
});
