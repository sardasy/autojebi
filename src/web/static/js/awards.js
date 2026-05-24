(() => {
  const tbody = document.getElementById("awards-body");

  function escape(s) {
    return (s == null ? "" : String(s)).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  }

  function fmtPrice(n) {
    if (n == null) return "—";
    if (n >= 100000000) return (n / 100000000).toFixed(1) + "억";
    if (n >= 10000) return (n / 10000).toFixed(0) + "만";
    return n.toLocaleString();
  }

  function fmtRatio(r) {
    if (r == null) return "—";
    return (r * 100).toFixed(1) + "%";
  }

  async function loadAwards() {
    try {
      const r = await fetch("/api/v1/awards?days=365");
      const items = await r.json();
      if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">낙찰 데이터 없음 (award_collection_enabled=True 후 수집 필요)</td></tr>';
        return;
      }
      tbody.innerHTML = items.map(a => `
        <tr>
          <td>${escape(a.bid_title || a.source_bid_id || "—")}</td>
          <td>${escape(a.bid_organization)}</td>
          <td>${escape(a.winner_name)}</td>
          <td class="text-end">${fmtPrice(a.bid_estimated_price)}</td>
          <td class="text-end">${fmtPrice(a.award_price)}</td>
          <td class="text-end">${fmtRatio(a.award_ratio)}</td>
          <td>${a.award_date || "—"}</td>
        </tr>
      `).join("");
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-4">오류: ${escape(e.message)}</td></tr>`;
    }
  }

  async function loadCharts() {
    try {
      const hist = await (await fetch("/api/v1/awards/ratio-histogram?bucket=0.05")).json();
      if (hist.length) {
        new Chart(document.getElementById("chart-ratio"), {
          type: "bar",
          data: {
            labels: hist.map(h => (h.bucket * 100).toFixed(0) + "%"),
            datasets: [{ label: "건수", data: hist.map(h => h.count), backgroundColor: "#0d6efd" }],
          },
          options: { plugins: { legend: { display: false } } },
        });
      }
      const trend = await (await fetch("/api/v1/dashboard/award-trend?months=12")).json();
      if (trend.length) {
        new Chart(document.getElementById("chart-trend"), {
          type: "line",
          data: {
            labels: trend.map(t => t.month),
            datasets: [{ label: "평균 낙찰률", data: trend.map(t => t.avg_award_ratio), borderColor: "#198754", tension: 0.3, fill: false }],
          },
          options: { plugins: { legend: { display: false } } },
        });
      }
    } catch (e) {
      console.warn("award charts load failed", e);
    }
  }

  loadAwards();
  loadCharts();
})();
