const addUserForm = document.getElementById("add-user-form");
const addUserError = document.getElementById("add-user-error");
const teamTableBody = document.getElementById("team-table-body");

function fmtLastActive(v) {
  return v ? new Date(v).toLocaleString() : "Never";
}

async function renderTeamTable() {
  const users = await apiGet("/api/team/users");
  teamTableBody.innerHTML = "";
  for (const u of users) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${u.name}</td>
      <td>${u.email}</td>
      <td>${u.role}</td>
      <td>${u.total_messages}</td>
      <td>${fmtLastActive(u.last_active_at)}</td>
      <td><span class="status-pill ${u.active ? "active" : "inactive"}">${u.active ? "Active" : "Deactivated"}</span></td>
      <td></td>
    `;
    const actionTd = tr.lastElementChild;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "secondary-btn small";
    btn.textContent = u.active ? "Deactivate" : "Reactivate";
    btn.addEventListener("click", async () => {
      const action = u.active ? "deactivate" : "activate";
      await apiPost(`/api/team/users/${encodeURIComponent(u.email)}/${action}`);
      renderTeamTable();
    });
    actionTd.appendChild(btn);
    teamTableBody.appendChild(tr);
  }
}

addUserForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  addUserError.textContent = "";
  const body = {
    name: document.getElementById("new-user-name").value,
    email: document.getElementById("new-user-email").value,
    password: document.getElementById("new-user-password").value,
    role: document.getElementById("new-user-role").value,
  };
  const { ok, data } = await apiPost("/api/team/users", body);
  if (!ok) {
    addUserError.textContent = data.error || "Could not add user";
    return;
  }
  addUserForm.reset();
  renderTeamTable();
});

async function initTeam() {
  await renderTeamTable();
}

window.AqarIQPanels.team = initTeam;
