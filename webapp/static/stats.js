const STATS_API = window.AQARIQ_API_PREFIX || "/api";

function fmtUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

async function initStats() {
  const stats = await apiGet(`${STATS_API}/stats`);

  const grid = document.getElementById("stats-cards");
  grid.innerHTML = "";
  grid.appendChild(kpiCard("Total Transactions", stats.total_transactions.toLocaleString()));
  grid.appendChild(kpiCard("Areas Covered", stats.area_count));
  grid.appendChild(kpiCard("Data Range", `${stats.earliest} → ${stats.latest}`));
  grid.appendChild(kpiCard("Platform Uptime", fmtUptime(stats.uptime_seconds)));

  const freshnessEl = document.getElementById("stats-freshness");
  if (stats.latest_bulk_load) {
    const v = stats.latest_bulk_load;
    freshnessEl.textContent = `Data last refreshed: ${v.loaded_at} — ${v.row_count.toLocaleString()} transactions, ${v.date_range_start} to ${v.date_range_end} (source: ${v.source})`;
  } else {
    freshnessEl.textContent = "No dataset version recorded yet.";
  }
}

window.AqarIQPanels.stats = initStats;
