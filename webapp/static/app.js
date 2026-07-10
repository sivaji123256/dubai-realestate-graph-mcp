// Shared app shell: auth/session handling + panel navigation.
// Panel modules (dashboard.js, graph.js, health.js) register an init
// function on window.AqarIQPanels[name]; app.js calls it each time that
// panel is opened, so data is always refetched fresh.

window.AqarIQPanels = {};

const loginScreen = document.getElementById("login-screen");
const appShell = document.getElementById("app-shell");
const loginForm = document.getElementById("login-form");
const passwordInput = document.getElementById("password-input");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");
const navButtons = document.querySelectorAll(".nav-btn");

function showApp() {
  loginScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
  const active = document.querySelector(".nav-btn.active");
  if (active) activatePanel(active.dataset.panel);
}

function showLogin() {
  appShell.classList.add("hidden");
  loginScreen.classList.remove("hidden");
}

function activatePanel(name) {
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.panel === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  const init = window.AqarIQPanels[name];
  if (typeof init === "function") init();
}

navButtons.forEach((btn) => {
  btn.addEventListener("click", () => activatePanel(btn.dataset.panel));
});

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  showLogin();
});

async function checkSession() {
  const res = await fetch("/api/me");
  const data = await res.json();
  if (data.authenticated) {
    showApp();
  } else {
    showLogin();
  }
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: passwordInput.value }),
  });
  if (res.ok) {
    passwordInput.value = "";
    showApp();
  } else {
    const data = await res.json().catch(() => ({}));
    loginError.textContent = data.error || "Login failed";
  }
});

async function apiGet(url) {
  const res = await fetch(url);
  if (res.status === 401) {
    showLogin();
    throw new Error("Not authenticated");
  }
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

checkSession();
