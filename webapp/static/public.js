const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const messagesEl = document.getElementById("messages");
const quickPromptsEl = document.getElementById("quick-prompts");

let chatHistory = [];

const QUICK_PROMPTS = [
  { label: "Market snapshot", template: "What's the market like in " },
  { label: "Compare two areas", template: "Compare " },
  { label: "Look up a project", template: "Tell me about the project " },
  { label: "Near a metro station", template: "Which areas are popular near " },
];

QUICK_PROMPTS.forEach((p) => {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "quick-prompt-btn";
  btn.textContent = p.label;
  btn.addEventListener("click", () => {
    chatInput.value = p.template;
    chatInput.focus();
  });
  quickPromptsEl.appendChild(btn);
});

function addMessage(role, text, opts = {}) {
  const el = document.createElement("div");
  el.className = `msg ${role}` + (opts.pending ? " pending" : "") + (opts.error ? " error" : "");

  const textEl = document.createElement("span");
  textEl.textContent = text;
  el.appendChild(textEl);

  if (role === "assistant" && !opts.pending && !opts.error) {
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "copy-btn";
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", async () => {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = "Copied!";
      setTimeout(() => (copyBtn.textContent = "Copy"), 1500);
    });
    el.appendChild(copyBtn);
  }

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
    const res = await fetch("/api/public/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: chatHistory }),
    });
    const data = await res.json();
    pending.remove();

    if (!res.ok) {
      if (res.status === 429) {
        addMessage("assistant", "You've reached the free usage limit for now -- please try again in a bit.", { error: true });
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
