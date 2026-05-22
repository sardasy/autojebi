// Step 5에서 /feedback POST 와 inline 라벨링 구현 — 현재는 /bids 목록 표시까지
(() => {
  const form = document.getElementById("filter-form");
  const body = document.getElementById("bids-body");

  function escape(s) {
    return (s == null ? "" : String(s)).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  }

  function fmtPrice(n) {
    if (n == null) return "—";
    if (n >= 100000000) return (n / 100000000).toFixed(1) + "억";
    if (n >= 10000) return (n / 10000).toFixed(0) + "만";
    return n.toLocaleString();
  }

  function labelPill(label) {
    if (!label) return '<span class="text-muted">—</span>';
    const cls = `label-${label}`;
    const txt = { relevant: "관련", irrelevant: "관련 없음", watch: "관심" }[label] || label;
    return `<span class="label-pill ${cls}">${txt}</span>`;
  }

  async function load() {
    const params = new URLSearchParams(new FormData(form));
    body.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">로드 중…</td></tr>';
    try {
      const r = await fetch(`/api/v1/bids?${params.toString()}`);
      const bids = await r.json();
      if (!bids.length) {
        body.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">결과 없음</td></tr>';
        return;
      }
      body.innerHTML = bids.map(b => `
        <tr>
          <td>${escape(b.title)}</td>
          <td>${escape(b.organization)}</td>
          <td>${escape(b.category)}</td>
          <td class="text-end">${fmtPrice(b.estimated_price)}</td>
          <td>${b.relevance_score != null ? (b.relevance_score * 100).toFixed(0) + "%" : "—"}</td>
          <td>${labelPill(b.user_label)}</td>
          <td>${b.created_at ? b.created_at.slice(0, 10) : ""}</td>
          <td class="text-end">
            <button class="btn btn-xs btn-outline-success" disabled title="Step 5에서 활성화">👍</button>
            <button class="btn btn-xs btn-outline-danger" disabled title="Step 5에서 활성화">👎</button>
          </td>
        </tr>
      `).join("");
    } catch (e) {
      body.innerHTML = `<tr><td colspan="8" class="text-center text-danger py-4">오류: ${escape(e.message)}</td></tr>`;
    }
  }

  form.addEventListener("submit", e => { e.preventDefault(); load(); });
  load();
})();
