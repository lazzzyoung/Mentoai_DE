const form = document.getElementById("analysis-form");
const jobIdInput = document.getElementById("analysis-job-id");
const analyzeSelectedBtn = document.getElementById("analyze-selected-btn");
const recentSelection = document.getElementById("recent-selection");
const recentJobTitle = document.getElementById("recent-job-title");
const recentJobMeta = document.getElementById("recent-job-meta");
const loginGuide = document.getElementById("detail-login-guide");

const statusBox = document.getElementById("detail-status");
const emptyText = document.getElementById("analysis-empty");
const resultBox = document.getElementById("analysis-result");

const jobTitle = document.getElementById("analysis-job-title");
const jobCompany = document.getElementById("analysis-company");
const jobScore = document.getElementById("analysis-score-chip");
const jobSummary = document.getElementById("analysis-summary");
const jobStacks = document.getElementById("analysis-stacks");
const jobActions = document.getElementById("analysis-actions");
const jobTip = document.getElementById("analysis-tip");

const USER_SESSION_STORAGE_KEY = "mentoai_last_user_session_v1";
const LAST_SELECTED_JOB_STORAGE_KEY = "mentoai_last_selected_job_v1";

let currentSession = null;
let currentSelection = null;

const setStatus = (text) => {
  statusBox.textContent = text;
};

const toFriendlyMessage = (error, fallbackText) => {
  const raw =
    error instanceof Error ? error.message : typeof error === "string" ? error : "";

  if (!raw) return fallbackText;
  if (raw.includes("Failed to fetch")) {
    return "네트워크 연결이 불안정합니다. 잠시 후 다시 시도해 주세요.";
  }
  if (raw.includes("계정을 찾을 수 없습니다") || raw.includes("User not found")) {
    return "프로필 정보를 찾지 못했습니다. 추천 화면에서 다시 시작해 주세요.";
  }
  if (raw.includes("해당 공고를 찾을 수 없습니다")) {
    return "선택한 공고를 찾지 못했습니다. 다른 공고로 시도해 주세요.";
  }
  return fallbackText;
};

const loadUserSession = () => {
  try {
    const raw = window.localStorage?.getItem(USER_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const userId = Number(parsed?.user_id);
    if (!Number.isFinite(userId) || userId < 1) return null;
    return {
      user_id: userId,
      user_name: parsed.user_name ?? "",
      user_profile: parsed.user_profile ?? null,
    };
  } catch {
    return null;
  }
};

const loadLastSelection = () => {
  try {
    const raw = window.localStorage?.getItem(LAST_SELECTED_JOB_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const jobId = Number(parsed?.job_id);
    if (!Number.isFinite(jobId) || jobId < 1) return null;
    return {
      job_id: jobId,
      title: parsed.title ?? "",
      company: parsed.company ?? "",
      user_id: Number(parsed.user_id) || null,
    };
  } catch {
    return null;
  }
};

const saveLastSelection = (jobId, title = "", company = "") => {
  if (!currentSession?.user_id || !jobId) return;
  try {
    window.localStorage?.setItem(
      LAST_SELECTED_JOB_STORAGE_KEY,
      JSON.stringify({
        job_id: Number(jobId),
        title,
        company,
        user_id: currentSession.user_id,
        selected_at: Date.now(),
      }),
    );
  } catch {
    // ignore
  }
};

const resetResult = () => {
  emptyText.classList.remove("hidden");
  resultBox.classList.add("hidden");
};

const renderStacks = (stacks) => {
  jobStacks.innerHTML = "";
  if (!stacks.length) {
    const noStack = document.createElement("span");
    noStack.className = "subtle";
    noStack.textContent = "필요 역량 정보 없음";
    jobStacks.appendChild(noStack);
    return;
  }

  stacks.forEach((stack) => {
    const chip = document.createElement("span");
    chip.className = "stack-chip";
    chip.textContent = stack;
    jobStacks.appendChild(chip);
  });
};

const renderActions = (actions) => {
  jobActions.innerHTML = "";
  if (!actions.length) {
    const empty = document.createElement("p");
    empty.className = "subtle";
    empty.textContent = "실천 과제가 아직 없습니다.";
    jobActions.appendChild(empty);
    return;
  }

  actions.forEach((item) => {
    const el = document.createElement("div");
    el.className = "action-item";
    el.innerHTML = `
      <div class="action-meta">
        <span class="action-category">${item.category ?? "기타"}</span>
        <span class="action-up">+${item.expected_score_up ?? 0}점</span>
      </div>
      <p class="action-title">${item.item_name ?? "항목 없음"}</p>
      <p class="action-desc">${item.description ?? "-"}</p>
    `;
    jobActions.appendChild(el);
  });
};

const renderDetail = (detail) => {
  jobTitle.textContent = detail.job_title ?? "-";
  jobCompany.textContent = detail.company_name ?? "-";
  jobScore.textContent = `${detail.current_score ?? 0}점`;
  jobSummary.textContent = detail.analysis_summary ?? "-";
  jobTip.textContent = detail.interview_tip ?? "-";

  renderStacks(detail.required_tech_stack ?? []);
  renderActions(detail.action_plan ?? []);

  emptyText.classList.add("hidden");
  resultBox.classList.remove("hidden");
};

const renderSelectionCard = () => {
  if (!currentSelection) {
    recentSelection.classList.add("hidden");
    recentJobTitle.textContent = "-";
    recentJobMeta.textContent = "-";
    if (analyzeSelectedBtn) analyzeSelectedBtn.disabled = true;
    return;
  }

  recentSelection.classList.remove("hidden");
  recentJobTitle.textContent = currentSelection.title || `공고 #${currentSelection.job_id}`;
  recentJobMeta.textContent = currentSelection.company || "회사 정보 없음";
  if (analyzeSelectedBtn) analyzeSelectedBtn.disabled = false;
};

const getPathJobId = () => {
  const pathParts = window.location.pathname.split("/");
  const pathJobId = Number(pathParts[pathParts.length - 1]);
  return !Number.isNaN(pathJobId) && pathJobId > 0 ? pathJobId : null;
};

const getQueryUserId = () => {
  const params = new URLSearchParams(window.location.search);
  const queryUserId = Number(params.get("user_id") || params.get("userId"));
  return !Number.isNaN(queryUserId) && queryUserId > 0 ? queryUserId : null;
};

const requestAnalysis = async (jobId, userId) => {
  try {
    setStatus("공고 분석을 준비하는 중...");
    resetResult();

    const response = await fetch(`/api/v3/jobs/${jobId}/analyze/${userId}`, { method: "POST" });
    const data = await response.json();

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error(data?.detail ?? "해당 공고를 찾을 수 없습니다.");
      }
      throw new Error(data?.detail ?? "공고 분석에 실패했습니다.");
    }

    renderDetail(data);
    saveLastSelection(jobId, data?.job_title ?? "", data?.company_name ?? "");
    currentSelection = {
      job_id: Number(jobId),
      title: data?.job_title ?? currentSelection?.title ?? "",
      company: data?.company_name ?? currentSelection?.company ?? "",
      user_id: userId,
    };
    renderSelectionCard();
    setStatus("완료: 분석이 반영되었습니다.");
  } catch (error) {
    console.error("[analysis-error]", error);
    setStatus(
      `안내: ${toFriendlyMessage(error, "분석 결과를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")}`,
    );
  }
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentSession?.user_id) {
    setStatus("먼저 추천 페이지에서 프로필을 등록해 주세요.");
    return;
  }

  const jobId = Number(jobIdInput.value);
  if (!jobId || jobId < 1) {
    setStatus("공고 번호를 입력해 주세요.");
    return;
  }

  currentSelection = {
    job_id: jobId,
    title: currentSelection?.title ?? "",
    company: currentSelection?.company ?? "",
    user_id: currentSession.user_id,
  };
  renderSelectionCard();
  await requestAnalysis(jobId, currentSession.user_id);
});

analyzeSelectedBtn?.addEventListener("click", async () => {
  if (!currentSelection?.job_id) {
    setStatus("먼저 추천 페이지에서 공고를 선택해 주세요.");
    return;
  }
  if (!currentSession?.user_id) {
    setStatus("먼저 추천 페이지에서 프로필을 등록해 주세요.");
    return;
  }
  await requestAnalysis(currentSelection.job_id, currentSession.user_id);
});

const initialize = async () => {
  currentSession = loadUserSession();
  currentSelection = loadLastSelection();
  renderSelectionCard();

  if (!currentSession?.user_id) {
    if (loginGuide) {
      loginGuide.textContent = "먼저 추천 페이지에서 프로필을 등록해 주세요.";
    }
    setStatus("프로필 정보가 없어 분석을 시작할 수 없습니다.");
    return;
  }

  if (loginGuide) {
    loginGuide.textContent = `${currentSession.user_name || "회원"}님의 프로필로 분석합니다.`;
  }

  const pathJobId = getPathJobId();
  const queryUserId = getQueryUserId();
  const effectiveUserId = queryUserId && queryUserId > 0 ? queryUserId : currentSession.user_id;

  if (pathJobId && effectiveUserId) {
    currentSelection = {
      job_id: pathJobId,
      title: currentSelection?.title ?? "",
      company: currentSelection?.company ?? "",
      user_id: effectiveUserId,
    };
    renderSelectionCard();
    jobIdInput.value = String(pathJobId);
    await requestAnalysis(pathJobId, effectiveUserId);
    return;
  }

  if (currentSelection?.job_id) {
    jobIdInput.value = String(currentSelection.job_id);
    await requestAnalysis(currentSelection.job_id, effectiveUserId);
    return;
  }

  setStatus("추천 페이지에서 공고를 선택하면 자동으로 분석됩니다.");
};

initialize();
