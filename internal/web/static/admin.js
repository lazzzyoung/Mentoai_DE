/* 멘토AI 어드민 — 빌드 도구 없는 바닐라 JS */

const $ = (selector) => document.querySelector(selector);

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);

const dt = (value) => (value ? new Date(value).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" }) : "-");

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = String(body.detail);
    } catch { /* 본문 없음 */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

/* 백그라운드 작업 트리거 후 잠시 폴링 */
function pollAfterBackground() {
  let ticks = 0;
  const timer = setInterval(() => {
    ticks += 1;
    loadStats(); loadRuns();
    if (ticks >= 12) clearInterval(timer);
  }, 5000);
}

/* ---------- 대시보드 ---------- */

async function loadStats() {
  try {
    const s = await api("/api/v1/admin/stats");
    const schedule = s.schedule || {};
    $("#stat-model").textContent =
      `임베딩 ${s.embedding_model} (${s.embedding_dim}차원) ㅣ LLM ${s.gemini_model}` +
      (schedule.enabled && schedule.next_run
        ? ` ㅣ 다음 실행 ${dt(schedule.next_run)}` : ` ㅣ 스케줄 꺼짐`);
    const boxes = [
      ["브론즈 원본", s.bronze, s.sizes?.bronze_size],
      ["정제 공고", s.jobs, s.sizes?.jobs_size],
      ["임베딩", s.embeddings, s.sizes?.embeddings_size],
      ["인재", s.users],
      ["분석 캐시", s.cached_analyses],
      ...(s.last_run
        ? [[`최근 실행 #${s.last_run.id}`,
            s.last_run.status === "success" ? "성공" : s.last_run.status === "running" ? "실행중" : "실패"]]
        : []),
      ...(s.running?.length ? [["실행 중 작업", s.running.join(", ")]] : []),
    ];
    $("#stat-boxes").innerHTML = boxes
      .map(([k, v, sub]) => `
        <div class="stat">
          <span class="v">${esc(v)}</span>
          <span class="k">${esc(k)}${sub ? ` <em class="sz">${esc(sub)}</em>` : ""}</span>
        </div>`)
      .join("");
  } catch (error) {
    $("#stat-boxes").innerHTML = `<p class="hint">현황 조회 실패 — ${esc(error.message)}</p>`;
  }
}

/* ---------- 임베딩 운영 ---------- */

async function loadEmbeddingModels() {
  try {
    const info = await api("/api/v1/admin/embedding/models");
    const models = info.available || info.fastembed || [];
    $("#emb-model-list").innerHTML = models
      .map((m) => `<option value="${esc(m.model)}">${m.dim}차원${m.size_gb != null ? ` ${m.size_gb.toFixed(2)}GB` : " (API)"}</option>`)
      .join("");
  } catch { /* 목록 실패는 치명적이지 않음 */ }
}

async function switchEmbedding() {
  const provider = $("#emb-provider").value;
  const model = $("#emb-model").value.trim() || null;
  if (!confirm(`임베딩 모델을 ${provider}:${model || "기본값"}(으)로 전환할까요?\n기존 임베딩은 모두 재계산됩니다.`)) return;
  const button = $("#emb-switch-btn");
  button.disabled = true;
  try {
    const query = `provider=${encodeURIComponent(provider)}${model ? `&model=${encodeURIComponent(model)}` : ""}`;
    const r = await api(`/api/v1/admin/embedding/switch?${query}`, { method: "POST" });
    alert(`전환 시작: ${r.target} (${r.dim}차원) — 백그라운드에서 재임베딩됩니다.`);
    pollAfterBackground();
  } catch (error) { alert(error.message); }
  finally { button.disabled = false; }
}

async function rebuildEmbeddings() {
  if (!confirm("임베딩을 전량 재계산할까요? 현재 모델로 다시 계산합니다.")) return;
  try {
    await api("/api/v1/admin/embedding/rebuild", { method: "POST" });
    pollAfterBackground();
  } catch (error) { alert(error.message); }
}

/* ---------- 파이프라인 ---------- */

const statusBadge = (status) =>
  status === "success" ? '<span class="st ok">성공</span>'
  : status === "running" ? '<span class="st run">실행중</span>'
  : `<span class="st fail">${status === "failed" ? "실패" : esc(status)}</span>`;

async function loadRuns() {
  const body = $("#runs-body");
  try {
    const rows = await api("/api/v1/admin/pipeline-runs");
    body.innerHTML = rows.length
      ? rows.map((r) => `
        <tr>
          <td class="num">#${r.id}</td>
          <td>${statusBadge(r.status)}</td>
          <td class="num">${dt(r.started_at)}</td>
          <td class="num">${dt(r.finished_at)}</td>
          <td class="num">${r.scraped ?? "-"}</td>
          <td class="num">${r.silver_upserted ?? "-"}</td>
          <td class="num">${r.embedded ?? "-"}</td>
          <td class="sub">${esc(r.error ?? "")}</td>
        </tr>`).join("")
      : `<tr><td colspan="8" class="empty">실행 이력이 없습니다.</td></tr>`;
  } catch (error) {
    body.innerHTML = `<tr><td colspan="8" class="empty">조회 실패 — ${esc(error.message)}</td></tr>`;
  }
}

async function runPipeline() {
  const button = $("#run-btn");
  button.disabled = true;
  button.textContent = "시작 중…";
  try {
    await api("/api/v1/admin/pipeline", { method: "POST" });
    pollAfterBackground();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "즉시 실행";
  }
}

/* ---------- 공고 데이터 ---------- */

async function loadJobs() {
  const body = $("#jobs-body");
  const query = encodeURIComponent($("#job-query").value.trim());
  try {
    const rows = await api(`/api/v1/admin/jobs?query=${query}&limit=30`);
    body.innerHTML = rows.length
      ? rows.map((j) => `
        <tr>
          <td class="num">${j.id}</td>
          <td>${esc(j.source)}</td>
          <td><b>${esc(j.company ?? "-")}</b></td>
          <td>${esc(j.position ?? "-")}</td>
          <td class="sub">${esc((j.skill_tags || []).slice(0, 5).join(", "))}</td>
          <td class="num sub">${dt(j.updated_at)}</td>
          <td><button type="button" class="row-del" data-id="${j.id}" data-name="${esc((j.company ?? "") + " " + (j.position ?? ""))}">삭제</button></td>
        </tr>`).join("")
      : `<tr><td colspan="7" class="empty">공고가 없습니다.</td></tr>`;
    body.querySelectorAll(".row-del").forEach((el) =>
      el.addEventListener("click", async () => {
        if (!confirm(`공고를 삭제할까요?\n${el.dataset.name}\n(원본·임베딩·분석캐시 함께 삭제)`)) return;
        try {
          await api(`/api/v1/admin/jobs/${el.dataset.id}`, { method: "DELETE" });
          loadJobs(); loadStats();
        } catch (error) { alert(error.message); }
      })
    );
  } catch (error) {
    body.innerHTML = `<tr><td colspan="7" class="empty">조회 실패 — ${esc(error.message)}</td></tr>`;
  }
}

/* ---------- 인재 관리 ---------- */

let editingUserId = null;

function setEditMode(user) {
  editingUserId = user ? user.id : null;
  const form = $("#user-form");
  $("#user-edit-tag").hidden = !user;
  $("#user-cancel-btn").hidden = !user;
  $("#user-save-btn").textContent = user ? "수정 저장" : "등록";
  if (user) {
    form.username.value = user.username;
    form.username.readOnly = true;
    form.desired_job.value = user.desired_job;
    form.career_years.value = user.career_years;
  } else {
    form.reset();
    form.username.readOnly = false;
    form.career_years.value = 0;
  }
}

async function loadUsers() {
  const body = $("#users-body");
  try {
    const rows = await api("/api/v1/users");
    body.innerHTML = rows.length
      ? rows.map((u) => `
        <tr>
          <td class="num">${u.id}</td>
          <td><b>${esc(u.username)}</b></td>
          <td>${esc(u.desired_job)}</td>
          <td class="num">${u.career_years}년</td>
          <td>
            <button type="button" class="row-edit" data-id="${u.id}">수정</button>
            <button type="button" class="row-del" data-id="${u.id}">삭제</button>
          </td>
        </tr>`).join("")
      : `<tr><td colspan="5" class="empty">등록된 인재가 없습니다.</td></tr>`;
    body.querySelectorAll(".row-edit").forEach((el) =>
      el.addEventListener("click", () => {
        const user = rows.find((r) => String(r.id) === el.dataset.id);
        if (user) setEditMode(user);
        window.scrollTo({ top: 0, behavior: "smooth" });
      })
    );
    body.querySelectorAll(".row-del").forEach((el) =>
      el.addEventListener("click", async () => {
        if (!confirm("인재를 삭제하면 관련 분석 캐시도 삭제됩니다. 계속할까요?")) return;
        try {
          await api(`/api/v1/admin/users/${el.dataset.id}`, { method: "DELETE" });
          if (editingUserId === Number(el.dataset.id)) setEditMode(null);
          loadUsers(); loadCache(); loadStats();
        } catch (error) { alert(error.message); }
      })
    );
  } catch (error) {
    body.innerHTML = `<tr><td colspan="5" class="empty">조회 실패 — ${esc(error.message)}</td></tr>`;
  }
}

async function submitUser(event) {
  event.preventDefault();
  const form = event.target;
  const skills = form.skills.value.split(",").map((s) => s.trim()).filter(Boolean);
  const payload = {
    username: form.username.value.trim(),
    desired_job: form.desired_job.value.trim(),
    career_years: Number(form.career_years.value || 0),
    skills,
  };
  try {
    if (editingUserId) {
      await api(`/api/v1/admin/users/${editingUserId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      await api("/api/v1/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
    setEditMode(null);
    loadUsers(); loadStats();
  } catch (error) { alert(error.message); }
}

/* ---------- 분석 캐시 ---------- */

async function loadCache() {
  const body = $("#cache-body");
  try {
    const rows = await api("/api/v1/admin/cache");
    body.innerHTML = rows.length
      ? rows.map((c) => `
        <tr>
          <td>${esc(c.username)}</td>
          <td><b>${esc(c.company)}</b> <span class="sub">${esc(c.position ?? "")}</span></td>
          <td class="sub">${esc(c.model)}</td>
          <td class="num">${dt(c.created_at)}</td>
          <td><button type="button" class="row-del" data-job="${c.job_id}" data-user="${c.user_id}">삭제</button></td>
        </tr>`).join("")
      : `<tr><td colspan="5" class="empty">캐시가 없습니다.</td></tr>`;
    body.querySelectorAll(".row-del").forEach((el) =>
      el.addEventListener("click", async () => {
        try {
          await api(`/api/v1/admin/cache/${el.dataset.job}/${el.dataset.user}`, { method: "DELETE" });
          loadCache(); loadStats();
        } catch (error) { alert(error.message); }
      })
    );
  } catch (error) {
    body.innerHTML = `<tr><td colspan="5" class="empty">조회 실패 — ${esc(error.message)}</td></tr>`;
  }
}

async function clearCache() {
  if (!confirm("전체 분석 캐시를 삭제할까요? 삭제 후 첫 분석은 Gemini가 다시 호출됩니다.")) return;
  try {
    const r = await api("/api/v1/admin/cache", { method: "DELETE" });
    alert(`${r.deleted}건 삭제했습니다.`);
    loadCache(); loadStats();
  } catch (error) { alert(error.message); }
}

/* ---------- PWA ---------- */

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

const offlineBar = document.createElement("div");
offlineBar.className = "offline-bar";
offlineBar.textContent = "오프라인 상태입니다. 네트워크 연결 후 이용하세요.";
document.body.appendChild(offlineBar);
const syncOfflineBar = () => offlineBar.classList.toggle("show", !navigator.onLine);
window.addEventListener("online", syncOfflineBar);
window.addEventListener("offline", syncOfflineBar);
syncOfflineBar();

/* ---------- 초기화 ---------- */

$("#run-btn").addEventListener("click", runPipeline);
$("#refresh-btn").addEventListener("click", () => { loadRuns(); loadStats(); });
$("#job-search-btn").addEventListener("click", loadJobs);
$("#job-query").addEventListener("keydown", (e) => { if (e.key === "Enter") loadJobs(); });
$("#user-form").addEventListener("submit", submitUser);
$("#user-cancel-btn").addEventListener("click", () => setEditMode(null));
$("#cache-clear-btn").addEventListener("click", clearCache);
$("#emb-switch-btn").addEventListener("click", switchEmbedding);
$("#emb-rebuild-btn").addEventListener("click", rebuildEmbeddings);

loadStats(); loadRuns(); loadJobs(); loadUsers(); loadCache(); loadEmbeddingModels();
