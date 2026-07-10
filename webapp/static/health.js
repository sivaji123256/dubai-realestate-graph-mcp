let latencyChart = null;

async function initHealth() {
  const m = await apiGet("/api/metrics");

  const grid = document.getElementById("health-cards");
  grid.innerHTML = "";
  const uptimeMin = Math.round(m.uptime_seconds / 60);
  grid.appendChild(kpiCard("Uptime", uptimeMin < 60 ? `${uptimeMin} min` : `${(uptimeMin / 60).toFixed(1)} hr`));
  grid.appendChild(kpiCard("Total Requests", m.total_requests.toLocaleString()));
  grid.appendChild(kpiCard("Chat Messages", m.chat_message_count.toLocaleString()));
  grid.appendChild(kpiCard("Avg Latency", `${m.avg_latency_ms} ms`));
  grid.appendChild(kpiCard("Errors", m.error_count));
  grid.appendChild(kpiCard("Est. OpenAI Spend", `$${m.estimated_openai_spend_usd}`));

  const ctx = document.getElementById("chart-latency");
  if (latencyChart) latencyChart.destroy();
  latencyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: m.recent_latencies_ms.map((_, i) => i + 1),
      datasets: [
        {
          label: "Latency (ms)",
          data: m.recent_latencies_ms,
          borderColor: "#c9a24b",
          backgroundColor: "#c9a24b",
          tension: 0.2,
          pointRadius: 0,
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { ticks: { color: "#90a0bd" }, grid: { color: "#24314c" } },
      },
    },
  });
}

window.AqarIQPanels.health = initHealth;
