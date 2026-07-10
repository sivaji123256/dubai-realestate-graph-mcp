// Shared app shell: auth/session handling + panel navigation + role gating.
// Panel modules (dashboard.js, graph.js, team.js, health.js) register an
// init function on window.AqarIQPanels[name]; app.js calls it each time
// that panel is opened, so data is always refetched fresh.

window.AqarIQPanels = {};
window.AqarIQUser = null;

const loginScreen = document.getElementById("login-screen");
const appShell = document.getElementById("app-shell");
const loginForm = document.getElementById("login-form");
const emailInput = document.getElementById("email-input");
const passwordInput = document.getElementById("password-input");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");
const userBadge = document.getElementById("user-badge");
const navButtons = document.querySelectorAll(".nav-btn");

function applyRoleGating() {
  const isAdmin = window.AqarIQUser && window.AqarIQUser.role === "admin";
  document.querySelectorAll(".admin-only").forEach((el) => el.classList.toggle("hidden", !isAdmin));
  // If a non-admin somehow lands on an admin panel, bounce to chat.
  const active = document.querySelector(".nav-btn.active");
  if (!isAdmin && active && active.classList.contains("admin-only")) {
    activatePanel("chat");
  }
}

function showApp() {
  loginScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
  if (window.AqarIQUser) {
    userBadge.textContent = `${window.AqarIQUser.name} · ${window.AqarIQUser.role}`;
  }
  applyRoleGating();
  const active = document.querySelector(".nav-btn.active");
  if (active) activatePanel(active.dataset.panel);
}

function showLogin() {
  appShell.classList.add("hidden");
  loginScreen.classList.remove("hidden");
  window.AqarIQUser = null;
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
    window.AqarIQUser = data;
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
    body: JSON.stringify({ email: emailInput.value, password: passwordInput.value }),
  });
  const data = await res.json().catch(() => ({}));
  if (res.ok) {
    passwordInput.value = "";
    window.AqarIQUser = { email: emailInput.value, name: data.name, role: data.role };
    showApp();
  } else {
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

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (res.status === 401) {
    showLogin();
    throw new Error("Not authenticated");
  }
  return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
}

checkSession();
