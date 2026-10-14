const $ = (id) => document.getElementById(id);
const form = $("ticketForm");
let tickets = [];
let searchTimer;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function toast(message) {
  const node = $("toast"); node.textContent = message; node.style.display = "block";
  setTimeout(() => { node.style.display = "none"; }, 2600);
}
async function request(url, options = {}) {
  const response = await fetch(url, {headers: {"Content-Type":"application/json"}, ...options});
  if (!response.ok) {
    let message = "Request failed";
    try { const data = await response.json(); message = data.detail || message; } catch {}
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}
async function loadStats() {
  const stats = await request("/api/stats");
  for (const key of ["total","open","in_progress","resolved","urgent"]) $(key).textContent = stats[key] ?? 0;
}
async function loadTickets() {
  const params = new URLSearchParams();
  if ($("search").value.trim()) params.set("search", $("search").value.trim());
  if ($("statusFilter").value) params.set("status", $("statusFilter").value);
  if ($("categoryFilter").value) params.set("category", $("categoryFilter").value);
  try {
    tickets = await request("/api/tickets?" + params.toString());
    renderTickets();
    await loadStats();
  } catch (error) { $("ticketList").innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`; }
}
function renderTickets() {
  if (!tickets.length) { $("ticketList").innerHTML = '<p class="empty">No tickets yet. Create your first support ticket.</p>'; return; }
  $("ticketList").innerHTML = tickets.map(t => `
    <article class="ticket">
      <div class="ticket-top">
        <div><h3>#${t.id} · ${escapeHtml(t.subject)}</h3><div class="meta">${escapeHtml(t.customer_name)} · ${escapeHtml(t.email)} · ${new Date(t.created_at).toLocaleString()}</div></div>
        <div class="chips"><span class="chip ${escapeHtml(t.priority)}">${escapeHtml(t.priority)}</span><span class="chip ${escapeHtml(t.category)}">${escapeHtml(t.category)}</span><span class="chip ${escapeHtml(t.status)}">${escapeHtml(t.status)}</span></div>
      </div>
      <p>${escapeHtml(t.description.length > 180 ? t.description.slice(0,180) + "…" : t.description)}</p>
      <div class="ticket-actions">
        <button class="text-button" onclick="showDetails(${t.id})">View AI suggestion</button>
        <select aria-label="Update status for ticket ${t.id}" onchange="updateStatus(${t.id}, this.value)">
          ${["Open","In Progress","Resolved","Closed"].map(s => `<option ${s===t.status?"selected":""}>${s}</option>`).join("")}
        </select>
        <button class="delete-button" onclick="removeTicket(${t.id})">Delete</button>
      </div>
    </article>`).join("");
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true; button.textContent = "Creating...";
  $("formMessage").textContent = "";
  try {
    await request("/api/tickets", {method:"POST", body:JSON.stringify({
      customer_name:$("customer_name").value, email:$("email").value,
      subject:$("subject").value, description:$("description").value
    })});
    form.reset(); $("formMessage").textContent = "Ticket created and analyzed.";
    await loadTickets(); toast("Ticket created successfully");
  } catch(error) { $("formMessage").textContent = error.message; }
  finally { button.disabled = false; button.innerHTML = 'Create ticket <span>→</span>'; }
});
async function updateStatus(id, status) {
  try { await request(`/api/tickets/${id}`, {method:"PATCH", body:JSON.stringify({status})}); toast("Ticket status updated"); await loadTickets(); }
  catch(error) { toast(error.message); await loadTickets(); }
}
async function removeTicket(id) {
  if (!confirm(`Delete ticket #${id}? This cannot be undone.`)) return;
  try { await request(`/api/tickets/${id}`, {method:"DELETE"}); toast("Ticket deleted"); await loadTickets(); }
  catch(error) { toast(error.message); }
}
async function showDetails(id) {
  try {
    const t = await request(`/api/tickets/${id}`);
    $("detailTitle").textContent = `#${t.id} · ${t.subject}`;
    $("detailContent").innerHTML = `
      <div class="chips"><span class="chip ${escapeHtml(t.priority)}">${escapeHtml(t.priority)} priority</span><span class="chip ${escapeHtml(t.category)}">${escapeHtml(t.category)}</span></div>
      <div class="detail-block"><h3>Customer issue</h3><p>${escapeHtml(t.description)}</p></div>
      <div class="detail-block"><h3>AI-assisted summary</h3><p>${escapeHtml(t.ai_summary)}</p></div>
      <div class="detail-block"><h3>Suggested reply</h3><p>${escapeHtml(t.suggested_reply)}</p></div>
      <button class="secondary" onclick="copyReply()">Copy suggested reply</button>`;
    $("detailDialog").showModal();
    window.currentReply = t.suggested_reply;
  } catch(error) { toast(error.message); }
}
async function copyReply() {
  try { await navigator.clipboard.writeText(window.currentReply || ""); toast("Suggested reply copied"); }
  catch { toast("Clipboard access is unavailable in this browser"); }
}
$("closeDialog").addEventListener("click", () => $("detailDialog").close());
$("refresh").addEventListener("click", loadTickets);
$("statusFilter").addEventListener("change", loadTickets);
$("categoryFilter").addEventListener("change", loadTickets);
$("search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadTickets, 250); });
loadTickets();
