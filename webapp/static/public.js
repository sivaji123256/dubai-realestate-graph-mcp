const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const messagesEl = document.getElementById("messages");
const quickPromptsEl = document.getElementById("quick-prompts");
const reportBar = document.getElementById("report-bar");
const reportBtn = document.getElementById("report-btn");
const reportView = document.getElementById("report-view");
const reportContent = document.getElementById("report-content");

let chatHistory = [];
let qaLog = []; // {question, answer} pairs, for the report

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
  el.className = `msg ${role}` + (opts.error ? " error" : "");

  const textEl = document.createElement("span");
  textEl.textContent = text;
  el.appendChild(textEl);

  if (role === "assistant" && !opts.error) {
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

function createTrace() {
  const el = document.createElement("div");
  el.className = "agent-trace";
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function addTraceLine(trace, text) {
  const line = document.createElement("div");
  line.className = "trace-line pending";
  line.innerHTML = `<span class="trace-dot"></span><span class="trace-text">${text}</span>`;
  trace.appendChild(line);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return line;
}

function resolveTraceLine(line, summary) {
  line.classList.remove("pending");
  line.classList.add("done");
  line.querySelector(".trace-text").textContent += ` — ${summary}`;
}

function showReportBar() {
  reportBar.classList.remove("hidden");
}

function updateReportContent() {
  reportContent.innerHTML = "";
  for (const { question, answer } of qaLog) {
    const block = document.createElement("div");
    block.className = "report-qa";
    const q = document.createElement("div");
    q.className = "report-q";
    q.textContent = question;
    const a = document.createElement("div");
    a.className = "report-a";
    a.textContent = answer;
    block.appendChild(q);
    block.appendChild(a);
    reportContent.appendChild(block);
  }
}

reportBtn.addEventListener("click", () => {
  updateReportContent();
  window.print();
});

async function streamChat(text) {
  const pendingQueue = [];
  const trace = createTrace();
  let finalContent = null;

  let res;
  try {
    res = await fetch("/api/public/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: chatHistory }),
    });
  } catch (err) {
    addMessage("assistant", "Network error -- please try again.", { error: true });
    return;
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    addMessage("assistant", data.error || "Something went wrong.", { error: true });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      let event;
      try {
        event = JSON.parse(part.slice(6));
      } catch (e) {
        continue;
      }
      if (event.type === "tool_call") {
        pendingQueue.push(addTraceLine(trace, event.friendly));
      } else if (event.type === "tool_result") {
        const line = pendingQueue.shift();
        if (line) resolveTraceLine(line, event.summary);
      } else if (event.type === "final") {
        finalContent = event.content;
      }
    }
  }

  if (finalContent !== null) {
    addMessage("assistant", finalContent);
    chatHistory.push({ role: "user", content: text });
    chatHistory.push({ role: "assistant", content: finalContent });
    qaLog.push({ question: text, answer: finalContent });
    showReportBar();
  }
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = "";
  addMessage("user", text);
  await streamChat(text);
});
