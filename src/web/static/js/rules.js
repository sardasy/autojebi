// Step 4에서 /alert-rules CRUD 구현 — 현재는 목록 표시 + 자리표시
(() => {
  const body = document.getElementById("rules-body");

  function joinOrAll(arr) {
    if (!arr || !arr.length) return "전체";
    return arr.join(", ");
  }

  function priceRange(min, max) {
    if (min == null && max == null) return "—";
    return `${min ?? 0} ~ ${max ?? "∞"}`;
  }

  async function load() {
    try {
      const r = await fetch("/api/v1/alert-rules");
      if (!r.ok) {
        body.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">알림 룰 API 미구현 (Step 4)</td></tr>';
        return;
      }
      const rules = await r.json();
      if (!rules.length) {
        body.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">룰 없음</td></tr>';
        return;
      }
      body.innerHTML = rules.map(rule => `
        <tr>
          <td>${rule.name}</td>
          <td>${rule.enabled ? "✓" : "—"}</td>
          <td>${joinOrAll(rule.filter_sources)}</td>
          <td>${joinOrAll(rule.filter_categories)}</td>
          <td>${joinOrAll(rule.filter_organizations)}</td>
          <td>${priceRange(rule.min_price, rule.max_price)}</td>
          <td>${rule.min_relevance}</td>
          <td>${joinOrAll(rule.channels)}</td>
          <td class="text-end"><button class="btn btn-xs btn-outline-secondary" disabled>편집</button></td>
        </tr>
      `).join("");
    } catch (e) {
      body.innerHTML = `<tr><td colspan="9" class="text-center text-danger py-4">오류: ${e.message}</td></tr>`;
    }
  }

  document.getElementById("btn-new-rule").addEventListener("click", () => {
    alert("Step 4에서 룰 CRUD UI가 활성화됩니다.");
  });

  load();
})();
