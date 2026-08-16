import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render(pathname = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${pathname}`, {
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

test("server-renders the compact archive landing", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html[^>]*lang="ko"/i);
  assert.match(html, /<title>외교의 순서/);
  assert.match(html, /외교는 무엇을/);
  assert.match(html, /네 갈래로 읽기/);
  assert.match(html, /전체 시간축/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|SkeletonPreview/);
});

test("server-renders all analysis routes", async () => {
  const routes = [
    ["/timeline", /스물여덟 해의 외교/],
    ["/governments/roh", /노무현 정부의 외교정책 가지/],
    ["/transitions", /바뀌기 직전과/],
    ["/years/2025", /한 해의 외교를/],
    ["/sources", /비어 있는 해까지/],
  ];

  for (const [pathname, expected] of routes) {
    const response = await render(pathname);
    assert.equal(response.status, 200, pathname);
    assert.match(await response.text(), expected, pathname);
  }
});

test("keeps the data and metadata contracts in the finished site", async () => {
  const [page, governmentPage, yearPage, header, layout, packageJson, data, analysis] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/governments/roh/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/years/2025/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/SiteHeader.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../public/data.json", import.meta.url), "utf8"),
    readFile(new URL("../public/analysis-2025.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /fetch\("\/data\.json"/);
  assert.match(page, /href="\/timeline"/);
  assert.match(governmentPage, /TARGET_ADMINISTRATION = "노무현"/);
  assert.match(governmentPage, /aria-labelledby="graph-svg-title graph-svg-description"/);
  assert.match(header, /aria-current/);
  assert.match(header, /\/transitions/);
  assert.match(header, /\/years\/2025/);
  assert.match(yearPage, /fetch\("\/analysis-2025\.json"/);
  assert.match(governmentPage, /className="mobile-priority-list"/);
  assert.match(governmentPage, /role="group"/);
  assert.match(layout, /title: "외교의 순서/);
  assert.doesNotMatch(layout, /codex-preview|Starter Project|_sites-preview/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);

  const parsed = JSON.parse(data);
  assert.equal(parsed.meta.coverage.from, 1998);
  assert.equal(parsed.meta.coverage.to, 2025);
  assert.ok(parsed.priorities.some((priority) => priority.coverageYear === 2003));

  const parsedAnalysis = JSON.parse(analysis);
  assert.equal(parsedAnalysis.meta.coverageYear, 2025);
  assert.equal(parsedAnalysis.meta.status, "verified");
  assert.equal(parsedAnalysis.meta.externalDataUsed, false);
  assert.equal(parsedAnalysis.priorities.length, 7);
  assert.deepEqual(parsedAnalysis.priorities.map((priority) => priority.ordinal), [1, 2, 3, 4, 5, 6, 7]);
  assert.equal(parsedAnalysis.meta.pageCount, 171);
  assert.equal(parsedAnalysis.summary.priorityBodyWords, 1460);
  assert.equal(parsedAnalysis.summary.topThreeWordShare, 57.1);
  assert.equal(parsedAnalysis.actors.find((actor) => actor.id === "un")?.fullDocument, 320);
});
