const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const messagesEl = document.getElementById("messages");

let chatHistory = [];

function addMessage(role, text, opts = {}) {
  const el = document.createElement("div");
  el.className = `msg ${role}` + (opts.pending ? " pending" : "") + (opts.error ? " error" : "");
  el.textContent = text;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

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
      body: JSON.stringify({ message: text, history: chatHistory }),
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
    chatHistory.push({ role: "user", content: text });
    chatHistory.push({ role: "assistant", content: data.reply });
  } catch (err) {
    pending.remove();
    addMessage("assistant", "Network error -- please try again.", { error: true });
  }
});
