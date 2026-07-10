const areaSelect = document.getElementById("area-select");
const graphCanvas = document.getElementById("graph-canvas");
const graphLegend = document.getElementById("graph-legend");

const NODE_COLORS = {
  Area: "#c9a24b",
  Building: "#5b8dd6",
  Project: "#7dd3c0",
  MasterProject: "#a78bfa",
  MetroStation: "#e2935f",
  Mall: "#e28fd0",
  PropertyType: "#8fbf8f",
};

let visNetwork = null;
let areasLoaded = false;

async function initGraph() {
  if (!areasLoaded) {
    const areas = await apiGet("/api/graph/areas");
    for (const a of areas) {
      const opt = document.createElement("option");
      opt.value = a.name;
      opt.textContent = a.name;
      areaSelect.appendChild(opt);
    }
    areasLoaded = true;

    graphLegend.innerHTML = Object.entries(NODE_COLORS)
      .map(([type, color]) => `<span class="legend-item"><span class="legend-dot" style="background:${color}"></span>${type}</span>`)
      .join("");
  }
}

areaSelect.addEventListener("change", async () => {
  const area = areaSelect.value;
  if (!area) return;
  graphCanvas.innerHTML = '<p class="footnote">Loading subgraph…</p>';

  const data = await apiGet(`/api/graph/area-subgraph?area=${encodeURIComponent(area)}`);

  const nodes = new vis.DataSet(
    data.nodes.map((n) => ({
      id: n.id,
      label: n.label + (n.transaction_count ? `\n(${n.transaction_count})` : ""),
      color: NODE_COLORS[n.type] || "#888",
      shape: n.type === "Area" ? "star" : "dot",
      size: n.type === "Area" ? 26 : 14,
      font: { color: "#e8edf7", size: 12 },
    }))
  );
  const edges = new vis.DataSet(
    data.edges.map((e) => ({ from: e.from, to: e.to, color: "#3a4a6b", arrows: "to" }))
  );

  graphCanvas.innerHTML = "";
  visNetwork = new vis.Network(
    graphCanvas,
    { nodes, edges },
    {
      physics: { stabilization: true, barnesHut: { gravitationalConstant: -4000, springLength: 120 } },
      interaction: { hover: true },
    }
  );
});

window.AqarIQPanels.graph = initGraph;
