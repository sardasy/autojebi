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

  async function postLabel(bidId, label) {
    const reviewer = localStorage.getItem("autojebi.reviewer") || "anonymous";
    const r = await fetch("/api/v1/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bid_id: bidId, label, reviewer }),
    });
    if (!r.ok) throw new Error(`feedback POST ${r.status}`);
  }

  function bindLabelButtons() {
    body.querySelectorAll("[data-label]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const tr = btn.closest("tr");
        const bidId = tr.dataset.bidId;
        const label = btn.dataset.label;
        btn.disabled = true;
        try {
          await postLabel(bidId, label);
          tr.querySelector(".label-cell").innerHTML = labelPill(label);
        } catch (e) {
          alert("라벨 저장 실패: " + e.message);
          btn.disabled = false;
        }
      });
    });
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
        <tr data-bid-id="${b.id}">
          <td>${escape(b.title)}</td>
          <td>${escape(b.organization)}</td>
          <td>${escape(b.category)}</td>
          <td class="text-end">${fmtPrice(b.estimated_price)}</td>
          <td>${b.relevance_score != null ? (b.relevance_score * 100).toFixed(0) + "%" : "—"}</td>
          <td class="label-cell">${labelPill(b.user_label)}</td>
          <td>${b.created_at ? b.created_at.slice(0, 10) : ""}</td>
          <td class="text-end">
            <button class="btn btn-sm btn-outline-success" data-label="relevant" title="관련">👍</button>
            <button class="btn btn-sm btn-outline-warning" data-label="watch" title="관심">👁️</button>
            <button class="btn btn-sm btn-outline-danger" data-label="irrelevant" title="관련 없음">👎</button>
          </td>
        </tr>
      `).join("");
      bindLabelButtons();
    } catch (e) {
      body.innerHTML = `<tr><td colspan="8" class="text-center text-danger py-4">오류: ${escape(e.message)}</td></tr>`;
    }
  }

  form.addEventListener("submit", e => { e.preventDefault(); load(); });
  load();
})();
