const TICKER_API = window.AQARIQ_API_PREFIX || "/api";

async function loadTicker() {
  const track = document.getElementById("tickerTrack");
  if (!track) return;
  try {
    const areas = await apiGet(`${TICKER_API}/dashboard/top-areas?limit=10`);
    const renderTicks = () =>
      areas
        .map(
          (a) =>
            `<span class="tick"><span>${a.area}</span><span class="sep">·</span><span class="metric">${Math.round(a.avg_price_per_sqm).toLocaleString()} AED/sqm</span><span class="sep">·</span><span>${a.transaction_count.toLocaleString()} sales</span></span>`
        )
        .join("");
    track.innerHTML = renderTicks() + renderTicks();
  } catch (e) {
    track.innerHTML = '<span class="tick">Live feed unavailable right now.</span>';
  }
}

async function loadFreshness() {
  const el = document.getElementById("syncTime");
  if (!el) return;
  try {
    const stats = await apiGet(`${TICKER_API}/stats`);
    el.textContent = `Data through ${stats.latest}`;
  } catch (e) {
    el.textContent = "";
  }
}

loadTicker();
loadFreshness();
