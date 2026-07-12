// Shared shell for /public: tab switching + a public-safe apiGet. No auth
// concept here (unlike webapp/static/app.js's version) -- public routes
// never 401, only rate-limit with 429.

window.AqarIQPanels = {};

const navButtons = document.querySelectorAll(".nav-btn");

function activatePanel(name) {
  navButtons.forEach((b) => {
    const on = b.dataset.panel === name;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  const init = window.AqarIQPanels[name];
  if (typeof init === "function") init();
}

navButtons.forEach((btn) => {
  btn.addEventListener("click", () => activatePanel(btn.dataset.panel));
});

// Feature cards double as real navigation into the product -- clicking one
// switches to the relevant tab (and, for chat-linked cards, drops a
// starting question into the input) instead of being purely decorative.
document.querySelectorAll(".capability-card").forEach((card) => {
  card.addEventListener("click", () => {
    const panel = card.dataset.panel;
    if (panel) activatePanel(panel);
    const prompt = card.dataset.prompt;
    const input = document.getElementById("chat-input");
    if (prompt && input) {
      input.value = prompt;
      input.focus();
    }
    document.querySelector(".public-nav")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

async function apiGet(url) {
  const res = await fetch(url);
  if (res.status === 429) {
    throw new Error("Rate limit exceeded -- please try again in a bit.");
  }
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}
