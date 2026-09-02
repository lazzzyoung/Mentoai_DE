/* 멘토AI UI — 빌드 도구 없는 바닐라 JS */

const $ = (selector) => document.querySelector(selector);

const state = { userId: null };

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = String(body.detail);
    } catch { /* JSON 아닌 에러 응답은 상태코드만 표시 */ }
    throw new Error(detail);
  }
  return response.json();
}

const SEP = '<span class="sep">ㅣ</span>';

/* 보유 스킬과 일치한 스킬은 잡코리아 검색어처럼 빨강 처리 */
function metaLine(job) {
  const matched = new Set((job.matched_skills || []).map((s) => s.toLowerCase()));
  const skillsHtml = (job.skills || [])
    .slice(0, 4)
    .map((s) =>
      matched.has(String(s).toLowerCase()) ? `<em class="kw">${esc(s)}</em>` : esc(s)
    )
    .join(", ");
  return [esc(job.career), esc(job.location), skillsHtml].filter(Boolean).join(SEP);
}

/* ---------- 인재 선택 ---------- */

async function loadUsers() {
  const container = $("#users");
  try {
    const users = await api("/api/v1/users");
    if (!users.length) {
      container.innerHTML = `<p class="hint">등록된 인재가 없습니다. <code>mentoai seed</code> 실행 후 이용하세요.</p>`;
      return;
    }
    container.innerHTML = users
      .map(
        (u) => `
        <button type="button" class="person" data-id="${u.id}">
          <span class="p-name">${esc(u.username)}</span>
          <span class="p-spec">${esc(u.desired_job)} ㅣ 경력 ${esc(u.career_years)}년</span>
        </button>`
      )
      .join("");

    container.querySelectorAll(".person").forEach((el) => {
      el.addEventListener("click", () => {
        container.querySelectorAll(".person").forEach((c) => c.classList.remove("on"));
        el.classList.add("on");
        state.userId = Number(el.dataset.id);
        $("#recommend-btn").disabled = false;
        $("#detail-section").hidden = true;
      });
    });
  } catch (error) {
    container.innerHTML = `<p class="hint">인재 목록 조회 실패 — ${esc(error.message)}</p>`;
  }
}

/* ---------- 맞춤 공고 ---------- */

async function recommend() {
  const jobsSection = $("#jobs-section");
  const jobsEl = $("#jobs");
  const detailSection = $("#detail-section");
  const button = $("#recommend-btn");

  detailSection.hidden = true;
  button.disabled = true;
  button.textContent = "조회 중…";
  jobsSection.hidden = false;
  jobsEl.innerHTML = `<p class="hint">공고를 검색하고 있습니다.</p>`;

  try {
    const data = await api(`/api/v1/jobs/recommend/${state.userId}`, { method: "POST" });
    $("#jobs-for").textContent = `${data.user_name} 기준`;
    $("#jobs-cnt").textContent = `총 ${data.recommendations.length}건`;

    if (!data.recommendations.length) {
      jobsEl.innerHTML = `<p class="hint">검색 결과가 없습니다. <code>mentoai pipeline</code> 실행 후 다시 조회하세요.</p>`;
      return;
    }

    jobsEl.innerHTML = data.recommendations
      .map(
        (job) => `
        <button type="button" class="posting" data-id="${job.job_id}">
          <div class="po-left">
            <div class="po-company">${esc(job.company)}<span class="po-src">${job.source ? esc(job.source) : ""}</span></div>
            <div class="po-title">${esc(job.title)}</div>
            <div class="po-meta">${metaLine(job)}</div>
            <div class="po-reason">${esc(job.reason)}</div>
          </div>
          <div class="po-right">
            <div class="po-score">
              <span class="lb">적합도</span>
              <span class="vl">${esc(job.match_score)}<small>점</small></span>
            </div>
            <span class="po-analyze">분석</span>
          </div>
        </button>`
      )
      .join("");

    jobsEl.querySelectorAll(".posting").forEach((el) => {
      el.addEventListener("click", () => analyze(el));
    });
  } catch (error) {
    jobsEl.innerHTML = `<p class="hint">공고 조회 실패 — ${esc(error.message)}</p>`;
  } finally {
    button.disabled = false;
    button.textContent = "맞춤 공고 조회";
  }
}

/* ---------- 역량 분석 ---------- */

async function analyze(postingEl) {
  const jobId = postingEl.dataset.id;
  const detail = $("#detail");
  const section = $("#detail-section");

  document.querySelectorAll(".posting").forEach((el) => el.classList.remove("on"));
  postingEl.classList.add("on");

  section.hidden = false;
  detail.innerHTML = `
    <div class="loading">
      공고와 인재 정보를 비교 분석 중입니다. 최초 분석은 수 초 소요됩니다.
      <div class="rail"><i></i></div>
    </div>`;
  section.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    const r = await api(`/api/v1/jobs/${jobId}/analyze/${state.userId}`, { method: "POST" });
    detail.innerHTML = `
      <div class="report">
        <div class="rp-head">
          <div>
            <div class="rp-company">${esc(r.company_name)}</div>
            <div class="rp-title">${esc(r.job_title)}</div>
          </div>
          <div class="rp-score">
            <div class="lb">종합 평가 점수</div>
            <div class="vl">${esc(r.current_score)}<small> / ${esc(r.max_score)}점</small></div>
          </div>
        </div>
        <div class="rp-body">
          <p class="summary">${esc(r.analysis_summary)}</p>

          <h3>필수 기술 스택</h3>
          <div class="stack">${(r.required_tech_stack || []).map((t) => `<span>${esc(t)}</span>`).join("")}</div>

          <h3>보완 액션 플랜</h3>
          <ol class="plan">
            ${(r.action_plan || []).map((a, i) => `
              <li>
                <span class="no">${i + 1}.</span>
                <span>
                  <span class="cat">[${esc(a.category)}]</span>
                  <span class="nm">${esc(a.item_name)}</span>
                  <div class="ds">${esc(a.description)}</div>
                </span>
                <span class="up">+${esc(a.expected_score_up)}점</span>
              </li>`).join("")}
          </ol>

          <h3>면접 TIP</h3>
          <p class="tip">${esc(r.interview_tip)}</p>
        </div>
      </div>`;
  } catch (error) {
    detail.innerHTML = `<p class="hint">분석 실패 — ${esc(error.message)}</p>`;
  }
}

$("#recommend-btn").addEventListener("click", recommend);
loadUsers();

/* ---------- 로그인 (구글/앱인토스 — 서버 설정이 켜져 있을 때만 표시) ---------- */

async function loadAuth() {
  const area = $("#auth-area");
  if (!area) return;

  let me = null;
  try { me = await api("/api/v1/auth/me"); } catch { /* 미로그인 */ }
  if (me) {
    area.innerHTML =
      `<b>${esc(me.username)}</b>님 <span class="bar">ㅣ</span>` +
      `<a href="#" class="util-link" id="logout-link">로그아웃</a>`;
    $("#logout-link").addEventListener("click", async (e) => {
      e.preventDefault();
      try { await api("/api/v1/auth/logout", { method: "POST" }); } catch { /* 이미 만료 */ }
      loadAuth();
    });
    return;
  }

  try {
    const status = await api("/api/v1/auth/status");
    const links = [];
    for (const p of status.providers || []) {
      if (!p.enabled) continue;
      if (p.login_path) {
        links.push(`<a class="util-link" href="${esc(p.login_path)}">구글로 로그인</a>`);
      } else if (p.provider === "toss" && typeof window.appLogin === "function") {
        // 앱인토스 웹뷰 안에서만 SDK(appLogin)가 존재한다
        links.push(`<a href="#" class="util-link" id="toss-login">토스로 로그인</a>`);
      }
    }
    if (links.length) area.innerHTML = links.join('<span class="bar">ㅣ</span>');
  } catch { /* status 조회 실패 시 기본 링크 유지 */ }

  const tossBtn = $("#toss-login");
  if (tossBtn) {
    tossBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        const { authorizationCode, referrer } = await window.appLogin();
        await api("/api/v1/auth/toss/callback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ authorizationCode, referrer }),
        });
        loadAuth();
      } catch (err) { alert(`토스 로그인 실패 — ${err.message}`); }
    });
  }
}

loadAuth();

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
