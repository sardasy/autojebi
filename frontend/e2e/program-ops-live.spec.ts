import { test } from "@playwright/test";

import { API_BASE, apiHeaders, postApi } from "./helpers";

const LIVE_KEYWORD = process.env.E2E_LIVE_KEYWORD || "변압기";

test.describe("program ops-live smoke", () => {
  test.skip(process.env.E2E_OPS_LIVE !== "1", "set E2E_OPS_LIVE=1 to run ops-live E2E");

  test("live G2B search, analyze, grade, document, and HWP agent smoke", async ({
    request,
  }) => {
    const hwpHealth = await request.get(`${API_BASE}/documents/hwp-agent/health`, {
      headers: apiHeaders(false),
    });
    test.skip(
      !hwpHealth.ok(),
      `HWP health endpoint unavailable: ${hwpHealth.status()} ${await hwpHealth.text()}`,
    );
    const hwpHealthBody = await hwpHealth.json();

    const search = await postApi(request, "/notices/search", {
      keyword: LIVE_KEYWORD,
      page: 1,
      page_size: 5,
    });
    test.skip(
      search.status() === 502,
      `G2B live search unavailable: ${await search.text()}`,
    );
    if (!search.ok()) {
      throw new Error(`live search failed: ${search.status()} ${await search.text()}`);
    }
    const searchBody = await search.json();
    test.skip(searchBody.items.length === 0, `no live G2B results for ${LIVE_KEYWORD}`);

    const item = searchBody.items[0];
    const upsert = await request.post(`${API_BASE}/notices/upsert`, {
      headers: apiHeaders(),
      data: {
        notice_no: item.notice_no,
        title: item.title,
        source: item.source,
        raw: item.raw,
      },
    });
    if (!upsert.ok()) {
      throw new Error(`live upsert failed: ${upsert.status()} ${await upsert.text()}`);
    }

    const analyze = await postApi(request, `/notices/${encodeURIComponent(item.notice_no)}/analyze`);
    test.skip(
      analyze.status() === 502,
      `Claude analysis unavailable: ${await analyze.text()}`,
    );
    if (!analyze.ok()) {
      throw new Error(`live analyze failed: ${analyze.status()} ${await analyze.text()}`);
    }

    const grade = await postApi(request, `/notices/${encodeURIComponent(item.notice_no)}/grade`, {
      alert: false,
    });
    if (!grade.ok()) {
      throw new Error(`live grade failed: ${grade.status()} ${await grade.text()}`);
    }

    const docs = await postApi(request, `/notices/${encodeURIComponent(item.notice_no)}/documents/analyze`);
    if (!docs.ok()) {
      throw new Error(`live document analyze failed: ${docs.status()} ${await docs.text()}`);
    }

    const spec = await postApi(request, `/notices/${encodeURIComponent(item.notice_no)}/spec-items/extract`);
    if (!spec.ok()) {
      throw new Error(`live spec extract failed: ${spec.status()} ${await spec.text()}`);
    }

    test.skip(
      !hwpHealthBody.ok,
      `HWP agent unavailable at ${hwpHealthBody.base_url}: ${hwpHealthBody.detail ?? "health=false"}`,
    );

    const compose = await postApi(
      request,
      `/notices/${encodeURIComponent(item.notice_no)}/documents/hwp-compose`,
      {
        include_bid_form: false,
        include_technical_compliance: true,
      },
    );
    test.skip(
      compose.status() === 502 || compose.status() === 409,
      `HWP agent or spec prerequisites unavailable: ${await compose.text()}`,
    );
    if (!compose.ok()) {
      throw new Error(`live hwp compose failed: ${compose.status()} ${await compose.text()}`);
    }

    const proposal = await postApi(
      request,
      `/notices/${encodeURIComponent(item.notice_no)}/documents/proposal-compose`,
      {},
    );
    test.skip(
      proposal.status() === 502 || proposal.status() === 409,
      `HWP proposal prerequisites unavailable: ${await proposal.text()}`,
    );
    if (!proposal.ok()) {
      throw new Error(`live proposal compose failed: ${proposal.status()} ${await proposal.text()}`);
    }
  });
});
