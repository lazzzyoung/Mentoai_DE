const form = document.getElementById("user-form");
const userNameInput = document.getElementById("user-name-input");
const desiredJobInput = document.getElementById("desired-job-input");
const careerYearsInput = document.getElementById("career-years-input");
const skillsInput = document.getElementById("skills-input");
const clearSessionBtn = document.getElementById("clear-session-btn");
const continueSessionBtn = document.getElementById("continue-session-btn");
const sessionEmptyHint = document.getElementById("session-empty-hint");
const sessionBadge = document.getElementById("session-badge");
const statusMessage = document.getElementById("status-message");
const pipelineSteps = document.querySelectorAll("#pipeline-steps li");

const userProfileCard = document.getElementById("user-profile-card");
const profileName = document.getElementById("profile-name");
const profileDesiredJob = document.getElementById("profile-desired-job");
const profileCareer = document.getElementById("profile-career");
const profileSkills = document.getElementById("profile-skills");

const jobCount = document.getElementById("job-count");
const avgMatchScore = document.getElementById("avg-match-score");
const topMatchScore = document.getElementById("top-match-score");
const jobList = document.getElementById("job-list");
const jobSearchInput = document.getElementById("job-search-input");
const jobSearchReset = document.getElementById("job-search-reset");
const jobSortSelect = document.getElementById("job-sort-select");
const jobPageSizeSelect = document.getElementById("job-page-size-select");
const jobPrevBtn = document.getElementById("job-prev-page");
const jobNextBtn = document.getElementById("job-next-page");
const jobPageInfo = document.getElementById("job-page-info");

const bookmarkList = document.getElementById("bookmark-list");
const bookmarkClearBtn = document.getElementById("bookmark-clear");

const detailPlaceholder = document.getElementById("detail-placeholder");
const detailContent = document.getElementById("detail-content");
const detailTitle = document.getElementById("detail-title");
const detailCompany = document.getElementById("detail-company");
const detailLink = document.getElementById("go-detail-page");
const detailScore = document.getElementById("detail-score");
const detailSummary = document.getElementById("detail-summary");
const detailStacks = document.getElementById("detail-stacks");
const detailActions = document.getElementById("detail-actions");
const detailTip = document.getElementById("detail-tip");

const BOOKMARK_STORAGE_KEY = "mentoai_bookmark_jobs_v1";
const USER_SESSION_STORAGE_KEY = "mentoai_last_user_session_v1";
const LAST_SELECTED_JOB_STORAGE_KEY = "mentoai_last_selected_job_v1";
const DEFAULT_PAGE_SIZE = 5;
const DEFAULT_SORT = "score-desc";
const MIN_FETCH_LIMIT = 20;
const DETAIL_CLICK_DEBOUNCE_MS = 160;

let currentUserId = null;
let currentSelectedJobId = null;
let detailRequestToken = 0;
let detailAbortController = null;
let detailDebounceTimer = null;
let queuedDetailJob = null;
let allRecommendations = [];
let bookmarkJobs = [];
let jobPageState = {
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
  sort: DEFAULT_SORT,
  keyword: "",
};

const setStatus = (text) => {
  statusMessage.textContent = text;
};

const parseSkills = (value) =>
  (value || "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);

const toFriendlyMessage = (error, fallbackText) => {
  const raw =
    error instanceof Error ? error.message : typeof error === "string" ? error : "";

  if (!raw) return fallbackText;
  if (raw.includes("Failed to fetch")) {
    return "네트워크 연결이 불안정합니다. 잠시 후 다시 시도해 주세요.";
  }
  if (raw.includes("계정을 찾을 수 없습니다") || raw.includes("User not found")) {
    return "프로필 정보를 찾지 못했습니다. 다시 로그인해 주세요.";
  }
  if (raw.includes("해당 공고를 찾을 수 없습니다")) {
    return "선택한 공고를 찾지 못했습니다. 다른 공고를 선택해 주세요.";
  }
  if (raw.includes("생성")) {
    return "프로필 저장 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.";
  }
  return fallbackText;
};

const normalizeText = (value) => (value ?? "").toString().toLowerCase();

const toNumber = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const toPositiveInt = (value, fallback) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.floor(parsed);
};

const safeJobId = (jobId) => toNumber(jobId) ?? String(jobId);

const clampPage = (value, totalPages) => {
  if (!Number.isFinite(totalPages) || totalPages < 1) return 1;
  if (value < 1) return 1;
  if (value > totalPages) return totalPages;
  return value;
};

const getSelectedPageSize = () =>
  toPositiveInt(jobPageSizeSelect?.value, DEFAULT_PAGE_SIZE);

const getMaxPageSizeOption = () => {
  if (!jobPageSizeSelect?.options?.length) {
    return MIN_FETCH_LIMIT;
  }
  const optionValues = Array.from(jobPageSizeSelect.options)
    .map((option) => toPositiveInt(option.value, 0))
    .filter((value) => value > 0);

  if (!optionValues.length) {
    return MIN_FETCH_LIMIT;
  }
  return Math.max(...optionValues);
};

const getRecommendationFetchLimit = () =>
  Math.max(MIN_FETCH_LIMIT, getMaxPageSizeOption());

const buildRecommendationApiPath = (userId, limit) => {
  const params = new URLSearchParams();
  if (Number.isFinite(limit) && limit > 0) {
    params.set("limit", String(Math.floor(limit)));
  }
  const query = params.toString();
  return query
    ? `/api/v3/jobs/recommend/${userId}?${query}`
    : `/api/v3/jobs/recommend/${userId}`;
};

const getQueryUserId = () => {
  const params = new URLSearchParams(window.location.search);
  const userId = Number(params.get("user_id") || params.get("userId"));
  if (!Number.isFinite(userId) || userId < 1) return null;
  return userId;
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

const saveUserSession = (user) => {
  if (!user) return;
  try {
    window.localStorage?.setItem(
      USER_SESSION_STORAGE_KEY,
      JSON.stringify({
        user_id: user.user_id,
        user_name: user.user_name,
        user_profile: user.user_profile ?? null,
        last_login_at: Date.now(),
      }),
    );
  } catch {
    // ignore
  }
};

const clearUserSession = () => {
  try {
    window.localStorage?.removeItem(USER_SESSION_STORAGE_KEY);
  } catch {
    // ignore
  }
};

const saveLastSelectedJob = (job) => {
  if (!job?.job_id || !currentUserId) return;
  try {
    window.localStorage?.setItem(
      LAST_SELECTED_JOB_STORAGE_KEY,
      JSON.stringify({
        job_id: Number(job.job_id),
        company: job.company ?? "",
        title: job.title ?? "",
        user_id: currentUserId,
        selected_at: Date.now(),
      }),
    );
  } catch {
    // ignore
  }
};

const showSessionBadge = (profile) => {
  if (!sessionBadge || !profile) return;
  const displayName = profile.user_name ?? "회원";
  const desiredJob = profile.user_profile?.desired_job ?? "희망 직무 미입력";
  sessionBadge.textContent = `현재 프로필: ${displayName} · ${desiredJob}`;
  sessionBadge.classList.remove("hidden");
};

const resetSessionBadge = () => {
  if (!sessionBadge) return;
  sessionBadge.classList.add("hidden");
  sessionBadge.textContent = "";
};

const loadBookmarks = () => {
  try {
    const raw = window.localStorage?.getItem(BOOKMARK_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((item) => ({
      job_id: safeJobId(item?.job_id),
      company: item?.company ?? "미상 기업",
      title: item?.title ?? "제목 없음",
      match_score: item?.match_score ?? 0,
      saved_at: item?.saved_at ?? Date.now(),
    }));
  } catch {
    return [];
  }
};

const persistBookmarks = () => {
  try {
    window.localStorage?.setItem(BOOKMARK_STORAGE_KEY, JSON.stringify(bookmarkJobs));
  } catch {
    // ignore
  }
};

const isBookmarked = (jobId) => {
  const normalized = safeJobId(jobId);
  return bookmarkJobs.some((item) => safeJobId(item.job_id) === normalized);
};

const upsertBookmark = (job) => {
  const id = safeJobId(job?.job_id);
  if (id == null) return;

  const exists = bookmarkJobs.some((item) => safeJobId(item.job_id) === id);
  if (exists) {
    bookmarkJobs = bookmarkJobs.filter((item) => safeJobId(item.job_id) !== id);
  } else {
    bookmarkJobs = [
      ...bookmarkJobs,
      {
        job_id: id,
        company: job.company ?? "미상 기업",
        title: job.title ?? "제목 없음",
        match_score: job.match_score ?? 0,
        saved_at: Date.now(),
      },
    ];
  }

  persistBookmarks();
  renderBookmarks();
  applyJobListState();
};

const resetPipeline = () => {
  pipelineSteps.forEach((step) => step.classList.remove("active", "done"));
};

const markPipeline = (stepNumber, status) => {
  const step = document.querySelector(`#pipeline-steps li[data-step="${stepNumber}"]`);
  if (!step) return;
  step.classList.remove("active", "done");
  if (status === "active") step.classList.add("active");
  if (status === "done") step.classList.add("done");
};

const resetDetail = () => {
  if (detailDebounceTimer) {
    clearTimeout(detailDebounceTimer);
    detailDebounceTimer = null;
  }
  queuedDetailJob = null;
  detailRequestToken += 1;
  if (detailAbortController) {
    detailAbortController.abort();
    detailAbortController = null;
  }
  currentSelectedJobId = null;
  detailContent.classList.add("hidden");
  detailPlaceholder.classList.remove("hidden");
  detailPlaceholder.textContent = "왼쪽에서 공고를 선택하면 요약이 표시됩니다.";
  detailStacks.innerHTML = "";
  detailActions.innerHTML = "";
  if (detailLink) {
    detailLink.classList.add("hidden");
    detailLink.href = "/jobs/detail";
  }
};

const renderUserProfile = (recommendationResponse) => {
  profileName.textContent = recommendationResponse.user_name ?? "-";
  profileDesiredJob.textContent = recommendationResponse.user_profile?.desired_job ?? "-";
  profileCareer.textContent = `${recommendationResponse.user_profile?.career_years ?? 0}년`;
  const skills = recommendationResponse.user_profile?.skills ?? [];
  profileSkills.textContent = skills.length ? skills.join(", ") : "없음";
  userProfileCard.classList.remove("hidden");
};

const getFilteredRecommendations = () => {
  if (!allRecommendations.length) return [];
  const keyword = normalizeText(jobPageState.keyword);
  if (!keyword) return allRecommendations.slice();
  return allRecommendations.filter((job) => {
    const target = normalizeText(`${job.company ?? ""} ${job.title ?? ""} ${job.reason ?? ""}`);
    return target.includes(keyword);
  });
};

const getSortedRecommendations = (recommendations) => {
  const sorted = [...recommendations];
  switch (jobPageState.sort) {
    case "score-asc":
      return sorted.sort((a, b) => (a.match_score ?? 0) - (b.match_score ?? 0));
    case "company-asc":
      return sorted.sort((a, b) => normalizeText(a.company).localeCompare(normalizeText(b.company), "ko"));
    case "title-asc":
      return sorted.sort((a, b) => normalizeText(a.title).localeCompare(normalizeText(b.title), "ko"));
    case "title-desc":
      return sorted.sort((a, b) => normalizeText(b.title).localeCompare(normalizeText(a.title), "ko"));
    case "score-desc":
    default:
      return sorted.sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0));
  }
};

const renderJobs = (recommendations, totalCount, countLabel) => {
  if (!allRecommendations.length) {
    jobList.classList.add("empty");
    jobList.textContent = currentUserId
      ? "현재 추천 가능한 공고가 없습니다."
      : "프로필을 등록하면 추천 공고가 표시됩니다.";
    jobCount.textContent = "0건";
    jobPageInfo.textContent = "0 / 0";
    return;
  }

  if (!recommendations.length) {
    jobList.classList.add("empty");
    jobList.textContent = "검색 조건에 맞는 공고가 없습니다.";
    jobCount.textContent = countLabel ?? `${totalCount}건`;
    return;
  }

  jobList.classList.remove("empty");
  jobList.innerHTML = "";
  jobCount.textContent = countLabel ?? `${totalCount}건`;

  recommendations.forEach((job) => {
    const jobIdText = String(job.job_id);
    const card = document.createElement("article");
    card.className = "job-card";
    card.dataset.jobId = jobIdText;

    const isActive = currentSelectedJobId !== null && String(currentSelectedJobId) === jobIdText;
    const bookmarked = isBookmarked(job.job_id);
    if (isActive) card.classList.add("active");

    card.innerHTML = `
      <div class="job-head">
        <div>
          <div class="job-company">${job.company ?? "미상 기업"}</div>
          <p class="job-title">${job.title ?? "제목 없음"}</p>
        </div>
        <span class="score-pill">${job.match_score ?? 0}점</span>
      </div>
      <p class="job-reason">${job.reason ?? "추천 근거 없음"}</p>
    `;

    const actions = document.createElement("div");
    actions.className = "job-card-actions";

    const detailBtn = document.createElement("button");
    detailBtn.type = "button";
    detailBtn.className = "job-detail-btn";
    detailBtn.textContent = "요약 보기";
    detailBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      queueJobDetailFetch(job);
    });

    const bookmarkBtn = document.createElement("button");
    bookmarkBtn.type = "button";
    bookmarkBtn.className = `job-bookmark-btn${bookmarked ? " is-active" : ""}`;
    bookmarkBtn.textContent = bookmarked ? "★ 관심" : "☆ 관심";
    bookmarkBtn.setAttribute("aria-label", `${bookmarked ? "관심 공고에서 제거" : "관심 공고로 저장"}`);
    bookmarkBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      upsertBookmark(job);
    });

    actions.append(detailBtn, bookmarkBtn);
    card.appendChild(actions);

    card.addEventListener("click", () => {
      document.querySelectorAll(".job-card").forEach((item) => item.classList.remove("active"));
      card.classList.add("active");
      queueJobDetailFetch(job);
    });

    jobList.appendChild(card);
  });
};

const renderPagination = (totalCount) => {
  const totalPages = Math.max(1, Math.ceil(totalCount / jobPageState.pageSize));
  jobPageState.page = clampPage(jobPageState.page, totalPages);
  jobPageInfo.textContent = `${jobPageState.page} / ${totalPages}`;
  jobPrevBtn.disabled = totalCount === 0 || jobPageState.page <= 1;
  jobNextBtn.disabled = totalCount === 0 || jobPageState.page >= totalPages;
};

const renderMetrics = (jobs) => {
  if (!jobs.length) {
    avgMatchScore.textContent = "0점";
    topMatchScore.textContent = "0점";
    return;
  }
  const scores = jobs.map((job) => Number(job.match_score) || 0);
  const total = scores.reduce((acc, score) => acc + score, 0);
  const avg = Math.round(total / scores.length);
  const top = Math.max(...scores);
  avgMatchScore.textContent = `${avg}점`;
  topMatchScore.textContent = `${top}점`;
};

const applyJobListState = () => {
  jobPageState.pageSize = getSelectedPageSize();

  const filtered = getFilteredRecommendations();
  const sorted = getSortedRecommendations(filtered);
  const totalCount = sorted.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / jobPageState.pageSize));
  jobPageState.page = clampPage(jobPageState.page, totalPages);

  const start = (jobPageState.page - 1) * jobPageState.pageSize;
  const end = start + jobPageState.pageSize;
  const paged = sorted.slice(start, end);

  const isFiltering = Boolean(jobPageState.keyword) && allRecommendations.length !== totalCount;
  const countLabel = isFiltering
    ? `검색 ${totalCount}건 / 전체 ${allRecommendations.length}건`
    : `${totalCount}건`;

  renderMetrics(sorted);
  renderJobs(paged, totalCount, countLabel);
  renderPagination(totalCount);
};

const renderBookmarks = () => {
  if (!bookmarkJobs.length) {
    bookmarkList.classList.add("empty");
    bookmarkList.textContent = "저장된 관심 공고가 없습니다.";
    return;
  }

  const sorted = [...bookmarkJobs].sort((a, b) => (b.saved_at ?? 0) - (a.saved_at ?? 0));
  bookmarkList.classList.remove("empty");
  bookmarkList.innerHTML = "";

  sorted.forEach((job) => {
    const item = document.createElement("article");
    item.className = "bookmark-item";
    item.dataset.jobId = String(job.job_id);
    item.innerHTML = `
      <div class="bookmark-item-main">
        <p class="bookmark-item-company">${job.company ?? "미상 기업"}</p>
        <p class="bookmark-item-title">${job.title ?? "제목 없음"}</p>
      </div>
      <div class="bookmark-item-score">${job.match_score ?? 0}점</div>
    `;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "bookmark-remove-btn";
    removeBtn.textContent = "삭제";
    removeBtn.addEventListener("click", (event) => {
      event.preventDefault();
      bookmarkJobs = bookmarkJobs.filter(
        (item) => safeJobId(item.job_id) !== safeJobId(job.job_id),
      );
      persistBookmarks();
      renderBookmarks();
      applyJobListState();
    });

    const jumpBtn = document.createElement("button");
    jumpBtn.type = "button";
    jumpBtn.className = "bookmark-jump-btn";
    jumpBtn.textContent = "이어보기";
    jumpBtn.addEventListener("click", (event) => {
      event.preventDefault();
      saveLastSelectedJob(job);
      window.location.href = "/jobs/detail";
    });

    const actionArea = document.createElement("div");
    actionArea.className = "bookmark-item-actions";
    actionArea.append(jumpBtn, removeBtn);

    item.appendChild(actionArea);
    bookmarkList.appendChild(item);
  });
};

const renderDetail = (detail, selectedJob = null) => {
  detailPlaceholder.classList.add("hidden");
  detailContent.classList.remove("hidden");

  const selectedScore = Number(selectedJob?.match_score);
  const analysisScore = Number(detail.current_score);
  const displayScore = Number.isFinite(selectedScore)
    ? selectedScore
    : Number.isFinite(analysisScore)
      ? analysisScore
      : 0;

  detailTitle.textContent = detail.job_title ?? "-";
  detailCompany.textContent = detail.company_name ?? "-";
  detailScore.textContent = String(displayScore);
  detailSummary.textContent = detail.analysis_summary ?? "-";
  detailTip.textContent = detail.interview_tip ?? "-";

  detailStacks.innerHTML = "";
  const stacks = detail.required_tech_stack ?? [];
  if (!stacks.length) {
    const noStack = document.createElement("span");
    noStack.className = "subtle";
    noStack.textContent = "필요 역량 정보 없음";
    detailStacks.appendChild(noStack);
  } else {
    stacks.forEach((stack) => {
      const chip = document.createElement("span");
      chip.className = "stack-chip";
      chip.textContent = stack;
      detailStacks.appendChild(chip);
    });
  }

  detailActions.innerHTML = "";
  const actions = detail.action_plan ?? [];
  if (!actions.length) {
    const emptyAction = document.createElement("p");
    emptyAction.className = "subtle";
    emptyAction.textContent = "실천 과제가 아직 없습니다.";
    detailActions.appendChild(emptyAction);
  } else {
    actions.forEach((action) => {
      const actionEl = document.createElement("div");
      actionEl.className = "action-item";
      actionEl.innerHTML = `
        <div class="action-meta">
          <span class="action-category">${action.category ?? "기타"}</span>
          <span class="action-up">+${action.expected_score_up ?? 0}점</span>
        </div>
        <p class="action-title">${action.item_name ?? "항목 없음"}</p>
        <p class="action-desc">${action.description ?? "-"}</p>
      `;
      detailActions.appendChild(actionEl);
    });
  }

  if (detailLink && currentSelectedJobId) {
    detailLink.classList.remove("hidden");
    detailLink.href = "/jobs/detail";
  }
};

const fetchJobDetail = async (job) => {
  const jobId = Number(job?.job_id);
  if (!currentUserId || !jobId) return;
  if (currentSelectedJobId === jobId && !detailContent.classList.contains("hidden")) return;
  currentSelectedJobId = jobId;
  detailRequestToken += 1;
  const requestToken = detailRequestToken;
  if (detailAbortController) {
    detailAbortController.abort();
  }
  detailAbortController = new AbortController();

  saveLastSelectedJob(job);

  detailPlaceholder.classList.remove("hidden");
  detailContent.classList.add("hidden");
  detailPlaceholder.textContent = "공고 요약을 불러오는 중...";

  try {
    const response = await fetch(`/api/v3/jobs/${jobId}/analyze/${currentUserId}`, {
      method: "POST",
      signal: detailAbortController.signal,
    });
    const data = await response.json();
    if (requestToken !== detailRequestToken) return;

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error("해당 공고를 찾을 수 없습니다.");
      }
      throw new Error(data?.detail ?? "공고 분석 요청에 실패했습니다.");
    }
    detailAbortController = null;
    renderDetail(data, job);
  } catch (error) {
    if (requestToken !== detailRequestToken) return;
    if (error?.name === "AbortError") return;
    console.error("[job-detail-error]", error);
    detailPlaceholder.classList.remove("hidden");
    detailContent.classList.add("hidden");
    detailPlaceholder.textContent = `안내: ${toFriendlyMessage(error, "공고 요약을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")}`;
  } finally {
    if (requestToken === detailRequestToken) {
      detailAbortController = null;
    }
  }
};

const queueJobDetailFetch = (job, { immediate = false } = {}) => {
  if (!job) return;

  if (detailDebounceTimer) {
    clearTimeout(detailDebounceTimer);
    detailDebounceTimer = null;
  }
  queuedDetailJob = job;

  if (immediate) {
    const targetJob = queuedDetailJob;
    queuedDetailJob = null;
    void fetchJobDetail(targetJob);
    return;
  }

  detailDebounceTimer = setTimeout(() => {
    detailDebounceTimer = null;
    const targetJob = queuedDetailJob;
    queuedDetailJob = null;
    if (!targetJob) return;
    void fetchJobDetail(targetJob);
  }, DETAIL_CLICK_DEBOUNCE_MS);
};

const fetchRecommendations = async (userId) => {
  resetPipeline();
  markPipeline(1, "active");
  setStatus("1/4 프로필을 확인하는 중...");

  resetDetail();
  userProfileCard.classList.add("hidden");
  jobList.classList.add("empty");
  jobList.textContent = "추천 공고를 불러오는 중...";
  jobCount.textContent = "0건";
  jobSearchInput.value = "";
  jobPageState.keyword = "";

  try {
    markPipeline(1, "done");
    markPipeline(2, "active");
    setStatus("2/4 내 정보를 불러오는 중...");

    const response = await fetch(
      buildRecommendationApiPath(userId, getRecommendationFetchLimit()),
      { method: "POST" },
    );
    const data = await response.json();

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error("User not found");
      }
      throw new Error(data?.detail ?? "추천 요청에 실패했습니다.");
    }

    markPipeline(2, "done");
    markPipeline(3, "active");
    setStatus("3/4 매칭 기준을 정리하는 중...");

    markPipeline(3, "done");
    markPipeline(4, "active");
    setStatus("4/4 추천 공고를 준비하는 중...");

    markPipeline(4, "done");
    setStatus("완료: 추천 결과를 준비했습니다.");

    currentUserId = data.user_id ?? userId;
    saveUserSession(data);
    showSessionBadge(data);

    if (sessionEmptyHint) {
      sessionEmptyHint.textContent = "최근 프로필로 바로 이어서 볼 수 있습니다.";
    }

    allRecommendations = data.recommendations ?? [];
    jobPageState = {
      ...jobPageState,
      page: 1,
      keyword: "",
      sort: DEFAULT_SORT,
      pageSize: getSelectedPageSize(),
    };
    jobSortSelect.value = jobPageState.sort;

    renderUserProfile(data);
    applyJobListState();

    if (allRecommendations.length > 0) {
      queueJobDetailFetch(allRecommendations[0], { immediate: true });
    }
  } catch (error) {
    console.error("[recommend-error]", error);
    allRecommendations = [];
    setStatus(
      `안내: ${toFriendlyMessage(error, "추천 공고를 불러오는 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")}`,
    );
    jobList.classList.add("empty");
    jobList.textContent = "추천 공고를 불러오지 못했습니다.";
    jobCount.textContent = "0건";
    renderMetrics([]);
    renderPagination(0);
  }
};

const performQuickLogin = async () => {
  const userName = (userNameInput?.value || "").trim();
  if (!userName) {
    throw new Error("이름을 입력해 주세요.");
  }

  const payload = {
    user_name: userName,
    desired_job: desiredJobInput?.value?.trim() || "미입력",
    career_years: Number(careerYearsInput?.value || 0),
    skills: parseSkills(skillsInput?.value),
  };

  const response = await fetch("/api/v3/auth/quick-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data?.detail ?? "프로필 저장에 실패했습니다.");
  }

  currentUserId = data.user_id;
  saveUserSession(data);
  showSessionBadge(data);
  return currentUserId;
};

const initializeFromSession = () => {
  const session = loadUserSession();
  if (!session) {
    if (sessionEmptyHint) {
      sessionEmptyHint.textContent = "처음 이용이라면 아래에서 프로필을 입력해 주세요.";
    }
    return null;
  }

  currentUserId = session.user_id;
  if (!userNameInput.value && session.user_name) {
    userNameInput.value = session.user_name;
  }
  if (!desiredJobInput.value && session.user_profile?.desired_job) {
    desiredJobInput.value = session.user_profile.desired_job;
  }
  if (!careerYearsInput.value && Number.isFinite(session.user_profile?.career_years)) {
    careerYearsInput.value = String(session.user_profile.career_years);
  }
  if (!skillsInput.value && Array.isArray(session.user_profile?.skills)) {
    skillsInput.value = session.user_profile.skills.join(", ");
  }
  showSessionBadge(session);
  if (sessionEmptyHint) {
    sessionEmptyHint.textContent = "최근 프로필을 찾았습니다. 바로 추천을 받아보세요.";
  }
  return session;
};

const resetPageState = () => {
  jobPageState = {
    ...jobPageState,
    page: 1,
    keyword: "",
  };
  jobSearchInput.value = "";
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const newUserId = await performQuickLogin();
    if (!newUserId || newUserId < 1) {
      throw new Error("프로필 저장에 실패했습니다.");
    }
    resetPageState();
    await fetchRecommendations(newUserId);
  } catch (error) {
    console.error("[quick-login-error]", error);
    setStatus(
      `안내: ${toFriendlyMessage(error, "프로필 저장 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")}`,
    );
  }
});

continueSessionBtn?.addEventListener("click", async () => {
  const session = loadUserSession();
  if (!session?.user_id) {
    setStatus("최근 프로필이 없습니다. 아래에서 프로필을 입력해 주세요.");
    return;
  }
  resetPageState();
  await fetchRecommendations(session.user_id);
});

jobSearchInput?.addEventListener("input", () => {
  jobPageState.keyword = jobSearchInput.value.trim();
  jobPageState.page = 1;
  applyJobListState();
});

jobSearchReset?.addEventListener("click", () => {
  jobPageState.keyword = "";
  jobSearchInput.value = "";
  jobPageState.page = 1;
  applyJobListState();
});

jobSortSelect?.addEventListener("change", () => {
  jobPageState.sort = jobSortSelect.value;
  jobPageState.page = 1;
  applyJobListState();
});

jobPageSizeSelect?.addEventListener("change", () => {
  jobPageState.page = 1;
  applyJobListState();
});

jobPrevBtn?.addEventListener("click", () => {
  jobPageState.page -= 1;
  applyJobListState();
});

jobNextBtn?.addEventListener("click", () => {
  jobPageState.page += 1;
  applyJobListState();
});

bookmarkClearBtn?.addEventListener("click", () => {
  if (!bookmarkJobs.length) return;
  bookmarkJobs = [];
  persistBookmarks();
  renderBookmarks();
  applyJobListState();
});

clearSessionBtn?.addEventListener("click", () => {
  clearUserSession();
  resetSessionBadge();
  currentUserId = null;
  currentSelectedJobId = null;
  allRecommendations = [];
  userProfileCard.classList.add("hidden");
  userNameInput.value = "";
  desiredJobInput.value = "";
  careerYearsInput.value = "";
  skillsInput.value = "";
  setStatus("프로필 정보를 초기화했습니다.");
  renderMetrics([]);
  renderPagination(0);
  jobList.classList.add("empty");
  jobList.textContent = "프로필을 등록하면 추천 공고가 표시됩니다.";
  if (sessionEmptyHint) {
    sessionEmptyHint.textContent = "프로필을 새로 입력해 시작해 주세요.";
  }
  resetDetail();
});

bookmarkJobs = loadBookmarks();
renderBookmarks();

const queryUserId = getQueryUserId();
const session = initializeFromSession();

if (queryUserId) {
  fetchRecommendations(queryUserId);
} else if (session?.user_id) {
  fetchRecommendations(session.user_id);
}
