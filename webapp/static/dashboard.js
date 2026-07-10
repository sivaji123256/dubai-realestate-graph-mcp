let topAreasChart = null;
let priceTrendChart = null;

document.getElementById("print-dashboard-btn").addEventListener("click", () => window.print());

function fmtAED(n) {
  if (n === null || n === undefined) return "—";
  return "AED " + Math.round(n).toLocaleString();
}

function kpiCard(label, value) {
  const div = document.createElement("div");
  div.className = "kpi-card";
  div.innerHTML = `<div class="kpi-value">${value}</div><div class="kpi-label">${label}</div>`;
  return div;
}

async function initDashboard() {
  const [kpis, topAreas, priceTrend, versions] = await Promise.all([
    apiGet("/api/dashboard/kpis"),
    apiGet("/api/dashboard/top-areas?limit=8"),
    apiGet("/api/dashboard/price-trend"),
    apiGet("/api/dataset/versions"),
  ]);

  const kpiGrid = document.getElementById("kpi-cards");
  kpiGrid.innerHTML = "";
  kpiGrid.appendChild(kpiCard("Total Transactions", kpis.total_transactions.toLocaleString()));
  kpiGrid.appendChild(kpiCard("Avg Price", fmtAED(kpis.avg_price)));
  kpiGrid.appendChild(kpiCard("Avg Price / sqm", fmtAED(kpis.avg_price_per_sqm)));
  kpiGrid.appendChild(kpiCard("Areas Covered", kpis.area_count));
  kpiGrid.appendChild(kpiCard("Data Range", `${kpis.earliest} → ${kpis.latest}`));

  const taCtx = document.getElementById("chart-top-areas");
  if (topAreasChart) topAreasChart.destroy();
  topAreasChart = new Chart(taCtx, {
    type: "bar",
    data: {
      labels: topAreas.map((r) => r.area),
      datasets: [
        {
          label: "Transactions",
          data: topAreas.map((r) => r.transaction_count),
          backgroundColor: "#c9a24b",
        },
      ],
    },
    options: {
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#90a0bd" }, grid: { color: "#24314c" } },
        y: { ticks: { color: "#e8edf7" }, grid: { display: false } },
      },
    },
  });

  const ptCtx = document.getElementById("chart-price-trend");
  if (priceTrendChart) priceTrendChart.destroy();
  priceTrendChart = new Chart(ptCtx, {
    data: {
      labels: priceTrend.map((r) => r.month),
      datasets: [
        {
          type: "line",
          label: "Avg price/sqm (AED)",
          data: priceTrend.map((r) => Math.round(r.avg_price_per_sqm)),
          borderColor: "#7dd3c0",
          backgroundColor: "#7dd3c0",
          yAxisID: "y",
          tension: 0.3,
        },
        {
          type: "bar",
          label: "Transactions",
          data: priceTrend.map((r) => r.transaction_count),
          backgroundColor: "#2a3a5c",
          yAxisID: "y1",
        },
      ],
    },
    options: {
      plugins: { legend: { labels: { color: "#e8edf7" } } },
      scales: {
        x: { ticks: { color: "#90a0bd" }, grid: { color: "#24314c" } },
        y: { position: "left", ticks: { color: "#7dd3c0" }, grid: { color: "#24314c" } },
        y1: { position: "right", ticks: { color: "#90a0bd" }, grid: { display: false } },
      },
    },
  });

  const versionEl = document.getElementById("dataset-version");
  if (versions.length) {
    const v = versions[0];
    versionEl.textContent = `Data last refreshed: ${v.loaded_at} — ${v.row_count.toLocaleString()} transactions, ${v.date_range_start} to ${v.date_range_end} (source: ${v.source})`;
  } else {
    versionEl.textContent = "No dataset version recorded yet.";
  }
}

window.AqarIQPanels.dashboard = initDashboard;
