const loginScreen = document.getElementById("login-screen");
const chatScreen = document.getElementById("chat-screen");
const loginForm = document.getElementById("login-form");
const passwordInput = document.getElementById("password-input");
const loginError = document.getElementById("login-error");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const messagesEl = document.getElementById("messages");

let history = [];

function showChat() {
  loginScreen.classList.add("hidden");
  chatScreen.classList.remove("hidden");
  chatInput.focus();
}

function showLogin() {
  chatScreen.classList.add("hidden");
  loginScreen.classList.remove("hidden");
}

function addMessage(role, text, opts = {}) {
  const el = document.createElement("div");
  el.className = `msg ${role}` + (opts.pending ? " pending" : "") + (opts.error ? " error" : "");
  el.textContent = text;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

async function checkSession() {
  const res = await fetch("/api/me");
  const data = await res.json();
  if (data.authenticated) {
    showChat();
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
    showChat();
  } else {
    const data = await res.json().catch(() => ({}));
    loginError.textContent = data.error || "Login failed";
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = "";
  addMessage("user", text);
  const pending = addMessage("assistant", "Thinking...", { pending: true });

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history }),
    });
    const data = await res.json();
    pending.remove();

    if (!res.ok) {
      if (res.status === 401) {
        showLogin();
        return;
      }
      addMessage("assistant", data.error || "Something went wrong.", { error: true });
      return;
    }

    addMessage("assistant", data.reply);
    history.push({ role: "user", content: text });
    history.push({ role: "assistant", content: data.reply });
  } catch (err) {
    pending.remove();
    addMessage("assistant", "Network error -- please try again.", { error: true });
  }
});

checkSession();
