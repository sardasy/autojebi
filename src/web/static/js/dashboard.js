// Step 3에서 stats/timeseries 엔드포인트와 연결 — 현재는 스캐폴드만
(() => {
  const palette = ["#0d6efd","#6f42c1","#d63384","#fd7e14","#ffc107","#198754","#20c997","#0dcaf0","#6c757d","#adb5bd"];

  async function loadStats(days) {
    try {
      const r = await fetch(`/api/v1/dashboard/stats?days=${days}`);
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (e) {
      console.warn("dashboard/stats 미구현 또는 오류", e);
      return null;
    }
  }

  function render(stats) {
    if (!stats) {
      document.querySelectorAll(".fs-3").forEach(el => el.textContent = "—");
      return;
    }
    document.getElementById("stat-total").textContent = stats.total ?? "—";
    document.getElementById("stat-avg-relevance").textContent = stats.avg_relevance != null ? stats.avg_relevance.toFixed(2) : "—";
    document.getElementById("stat-awarded").textContent = stats.awarded ?? "—";
    document.getElementById("stat-new").textContent = stats.new_count ?? "—";

    if (stats.by_source) {
      new Chart(document.getElementById("chart-source"), {
        type: "doughnut",
        data: { labels: Object.keys(stats.by_source), datasets: [{ data: Object.values(stats.by_source), backgroundColor: palette }] },
        options: { plugins: { legend: { position: "bottom" } } }
      });
    }
    if (stats.by_category) {
      new Chart(document.getElementById("chart-category"), {
        type: "pie",
        data: { labels: Object.keys(stats.by_category), datasets: [{ data: Object.values(stats.by_category), backgroundColor: palette }] },
        options: { plugins: { legend: { position: "bottom" } } }
      });
    }
    if (stats.top_organizations) {
      new Chart(document.getElementById("chart-org"), {
        type: "bar",
        data: { labels: stats.top_organizations.map(o => o.organization), datasets: [{ label: "공고수", data: stats.top_organizations.map(o => o.count), backgroundColor: palette[0] }] },
        options: { indexAxis: "y", plugins: { legend: { display: false } } }
      });
    }
  }

  async function loadTimeseries(days) {
    try {
      const r = await fetch(`/api/v1/dashboard/timeseries?days=${days}&metric=count`);
      if (!r.ok) throw new Error(r.status);
      const data = await r.json();
      new Chart(document.getElementById("chart-timeseries"), {
        type: "line",
        data: { labels: data.map(d => d.date), datasets: [{ label: "공고수", data: data.map(d => d.value), borderColor: palette[0], tension: 0.3, fill: false }] },
        options: { plugins: { legend: { display: false } } }
      });
    } catch (e) {
      console.warn("dashboard/timeseries 미구현 또는 오류", e);
    }
  }

  async function refresh() {
    const days = document.getElementById("days").value;
    const stats = await loadStats(days);
    render(stats);
    await loadTimeseries(days);
  }

  document.getElementById("days").addEventListener("change", refresh);
  refresh();
})();
