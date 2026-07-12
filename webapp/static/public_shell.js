// Shared shell for /public: tab switching + a public-safe apiGet. No auth
// concept here (unlike webapp/static/app.js's version) -- public routes
// never 401, only rate-limit with 429.

window.AqarIQPanels = {};

const navButtons = document.querySelectorAll(".nav-btn");

function activatePanel(name) {
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.panel === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  const init = window.AqarIQPanels[name];
  if (typeof init === "function") init();
}

navButtons.forEach((btn) => {
  btn.addEventListener("click", () => activatePanel(btn.dataset.panel));
});

async function apiGet(url) {
  const res = await fetch(url);
  if (res.status === 429) {
    throw new Error("Rate limit exceeded -- please try again in a bit.");
  }
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}
