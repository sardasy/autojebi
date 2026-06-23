import { test } from "@playwright/test";

import { API_BASE, apiHeaders, postApi } from "./helpers";

const LIVE_KEYWORD = process.env.E2E_LIVE_KEYWORD || "변압기";

test.describe("program ops-live smoke", () => {
  test.skip(process.env.E2E_OPS_LIVE !== "1", "set E2E_OPS_LIVE=1 to run ops-live E2E");

  test("live G2B search, analyze, grade, document, and HWP agent smoke", async ({
    request,
  }) => {
    // HWP 에이전트 가용성은 compose 직전에만 검사한다. 에이전트가 없어도
    // 라이브 G2B 검색→분석→그레이드→문서분석→규격추출은 끝까지 검증한다.
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
    // 같은 라이브 공고를 재실행하면 이미 분석/진행된 상태(409 invalid transition)일 수 있다.
    // 그 경우 공고는 이미 분석되어 있으므로 정상으로 간주하고 계속 진행한다.
    if (!analyze.ok() && analyze.status() !== 409) {
      throw new Error(`live analyze failed: ${analyze.status()} ${await analyze.text()}`);
    }

    // 재실행 시 공고가 이미 진행된 상태면 일부 단계가 409(invalid transition)를 반환할 수 있다.
    // 라이브 코어 스모크의 목적상 409(이미 처리됨)는 정상으로 간주한다.
    const okOr409 = (status: number) => status >= 200 && status < 300 || status === 409;

    const grade = await postApi(request, `/notices/${encodeURIComponent(item.notice_no)}/grade`, {
      alert: false,
    });
    if (!okOr409(grade.status())) {
      throw new Error(`live grade failed: ${grade.status()} ${await grade.text()}`);
    }

    const docs = await postApi(request, `/notices/${encodeURIComponent(item.notice_no)}/documents/analyze`);
    if (!okOr409(docs.status())) {
      throw new Error(`live document analyze failed: ${docs.status()} ${await docs.text()}`);
    }

    const spec = await postApi(request, `/notices/${encodeURIComponent(item.notice_no)}/spec-items/extract`);
    if (!okOr409(spec.status())) {
      throw new Error(`live spec extract failed: ${spec.status()} ${await spec.text()}`);
    }

    // ── 여기까지 라이브 코어(G2B/Claude/grade/문서/규격) 검증 완료 ──
    // HWP 에이전트가 도달 가능할 때만 compose/proposal까지 진행한다.
    const hwpHealth = await request.get(`${API_BASE}/documents/hwp-agent/health`, {
      headers: apiHeaders(false),
    });
    const hwpHealthBody = hwpHealth.ok() ? await hwpHealth.json() : { ok: false, base_url: "?", detail: `health endpoint ${hwpHealth.status()}` };
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
