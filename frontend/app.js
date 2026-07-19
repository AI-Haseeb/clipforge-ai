const API_BASE = "http://127.0.0.1:8000";

const STORAGE_KEYS = {
  lastJob: "clipforge_current_job_id",
  pendingJob: "clipforge_pending_job_id",
  lastStatus: "clipforge_last_status_message",
  authToken: "clipforge_auth_token",
  authUser: "clipforge_auth_user",
  theme: "clipforge_theme",
};

let mode = "upload";
let currentJobId = null;
let pollingTimer = null;
let isSubmitting = false;
let jobStartTimestamp = 0;
let seenProgressEvents = new Set();
let renderedProgressEvents = new Map();
let progressEventCounter = 0;

const uploadTab = document.getElementById("uploadTab");
const linkTab = document.getElementById("linkTab");
const uploadBox = document.getElementById("uploadBox");
const linkBox = document.getElementById("linkBox");

const generateBtn = document.getElementById("generateBtn");
const statusText = document.getElementById("statusText");
const progressBar = document.getElementById("progressBar");
const progressStep = document.getElementById("progressStep");
const progressPct = document.getElementById("progressPct");
const progressElapsed = document.getElementById("progressElapsed");
const progressEta = document.getElementById("progressEta");
const progressEvents = document.getElementById("progressEvents");
const progressEventsCount = document.getElementById("progressEventsCount");
const currentJobLabel = document.getElementById("currentJobLabel");
const resumeJobId = document.getElementById("resumeJobId");
const resumeJobBtn = document.getElementById("resumeJobBtn");
const clearJobBtn = document.getElementById("clearJobBtn");

const resultSection = document.getElementById("resultSection");
const shortsList = document.getElementById("shortsList");
const thumbsList = document.getElementById("thumbsList");
const metaList = document.getElementById("metaList");
const zipDownload = document.getElementById("zipDownload");
const filesList = document.getElementById("filesList");
const resultSummary = document.getElementById("resultSummary");
const resultTabs = document.querySelectorAll(".result-tab");
const creatorSteps = document.querySelectorAll(".creator-step");
const creatorStepPanels = document.querySelectorAll(".creator-step-panel");
const processingTimeline = document.getElementById("processingTimeline");
const flowSummaryCard = document.getElementById("flowSummaryCard");
const finalSummaryCard = document.getElementById("finalSummaryCard");
const captionPresetGrid = document.getElementById("captionPresetGrid");
const captionPreviewText = document.getElementById("captionPreviewText");
const captionPreviewVideo = document.getElementById("captionPreviewVideo");
const captionPreviewName = document.getElementById("captionPreviewName");
const captionPreviewDetails = document.getElementById("captionPreviewDetails");
const captionPreviewStyleState = document.getElementById("captionPreviewStyleState");
const captionPreviewFrame = document.querySelector(".preview-video-frame");
const musicPreviewAudio = document.getElementById("musicPreviewAudio");
const musicPreviewStatus = document.getElementById("musicPreviewStatus");
const musicTrackList = document.getElementById("musicTrackList");
const musicVolumeValue = document.getElementById("musicVolumeValue");
const refreshProjectInputBtn = document.getElementById("refreshProjectInputBtn");
const projectInputList = document.getElementById("projectInputList");
const projectInputRoot = document.getElementById("projectInputRoot");

const CAPTION_RENDER_SIZES = {
  extra_small: 28,
  small: 34,
  medium: 42,
  large: 52,
  extra_large: 62,
};

const CAPTION_PRESETS = [
  { value: "clean_white", name: "Clean White", sampleA: "TO GET", sampleB: "STARTED", family: "Montserrat", textCase: "uppercase" },
  { value: "bold_yellow", name: "Bold Yellow", sampleA: "TO GET", sampleB: "STARTED", family: "Montserrat", textCase: "uppercase" },
  { value: "podcast_blue", name: "Podcast Blue", sampleA: "TO GET", sampleB: "STARTED", family: "Montserrat", textCase: "uppercase" },
  { value: "gaming_neon", name: "Gaming Neon", sampleA: "TO GET", sampleB: "STARTED", family: "Montserrat", textCase: "uppercase" },
  { value: "horror_red", name: "Horror Red", sampleA: "DON'T", sampleB: "LOOK AWAY", family: "Montserrat", textCase: "uppercase" },
  { value: "meme_big", name: "Meme Big", sampleA: "WAIT", sampleB: "WHAT", family: "Montserrat", textCase: "uppercase" },
  { value: "viral_dynamic", name: "Viral Dynamic", sampleA: "TO GET", sampleB: "STARTED", family: "Poppins", textCase: "uppercase" },
  { value: "creator_pop", name: "Creator Pop", sampleA: "TURN THIS", sampleB: "INTO CLIPS", family: "Poppins", textCase: "uppercase" },
  { value: "scroll_stopper", name: "Scroll Stopper", sampleA: "STOP", sampleB: "SCROLLING", family: "Montserrat", textCase: "uppercase" },
  { value: "soft_glow", name: "Soft Glow", sampleA: "small actions", sampleB: "big impact", family: "Raleway", textCase: "lowercase" },
];
const EDITING_STYLE_PRESETS = {
  podcast: { name: "Podcast / Interview", filter: "Natural Enhance (Recommended)", fontPreset: "podcast_blue", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "podcast", musicVolume: "0.16", reframe: "on" },
  educational: { name: "Educational", filter: "Natural Enhance (Recommended)", fontPreset: "clean_white", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "educational", musicVolume: "0.14", reframe: "on" },
  tutorial: { name: "Tutorial / How-to", filter: "Cool Modern", fontPreset: "podcast_blue", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "tutorial", musicVolume: "0.12", reframe: "on" },
  motivational: { name: "Motivational", filter: "Warm Cinematic", fontPreset: "bold_yellow", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "motivational", musicVolume: "0.22", reframe: "on" },
  romantic: { name: "Romantic", filter: "Warm Cinematic", fontPreset: "soft_glow", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "normal", musicEnabled: true, musicCategory: "romantic", musicVolume: "0.18", reframe: "on" },
  sad: { name: "Sad / Emotional", filter: "Warm Cinematic", fontPreset: "podcast_blue", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "normal", musicEnabled: true, musicCategory: "sad", musicVolume: "0.17", reframe: "on" },
  love: { name: "Love Story", filter: "Warm Cinematic", fontPreset: "soft_glow", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "normal", musicEnabled: true, musicCategory: "love", musicVolume: "0.18", reframe: "on" },
  business: { name: "Business", filter: "Cool Modern", fontPreset: "clean_white", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "business", musicVolume: "0.12", reframe: "on" },
  marketing: { name: "Marketing / Sales", filter: "Punchy + Clear", fontPreset: "scroll_stopper", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "marketing", musicVolume: "0.20", reframe: "on" },
  gaming: { name: "Gaming", filter: "Punchy + Clear", fontPreset: "gaming_neon", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "gaming", musicVolume: "0.24", reframe: "on" },
  funny: { name: "Funny / Comedy", filter: "Punchy + Clear", fontPreset: "viral_dynamic", captionSize: "large", captionPosition: "center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "funny", musicVolume: "0.23", reframe: "on" },
  meme: { name: "Meme / Viral", filter: "Punchy + Clear", fontPreset: "meme_big", captionSize: "large", captionPosition: "center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "meme", musicVolume: "0.25", reframe: "on" },
  horror: { name: "Horror / Suspense", filter: "Black & White (Mono)", fontPreset: "horror_red", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "horror", musicVolume: "0.18", reframe: "on" },
  cinematic: { name: "Cinematic", filter: "Warm Cinematic", fontPreset: "clean_white", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "normal", musicEnabled: true, musicCategory: "cinematic", musicVolume: "0.20", reframe: "on" },
  documentary: { name: "Documentary", filter: "Natural Enhance (Recommended)", fontPreset: "clean_white", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "normal", musicEnabled: true, musicCategory: "documentary", musicVolume: "0.12", reframe: "on" },
  news: { name: "News / Commentary", filter: "Cool Modern", fontPreset: "clean_white", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: false, musicCategory: "none", musicVolume: "0.00", reframe: "on" },
  lifestyle: { name: "Lifestyle / Vlog", filter: "Natural Enhance (Recommended)", fontPreset: "creator_pop", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "lifestyle", musicVolume: "0.17", reframe: "on" },
  fitness: { name: "Fitness / Sports", filter: "Punchy + Clear", fontPreset: "gaming_neon", captionSize: "large", captionPosition: "bottom_center", fontFamily: "preset", captionCase: "preset", musicEnabled: true, musicCategory: "fitness", musicVolume: "0.24", reframe: "on" },
};


const topNav = document.querySelector(".top-nav");
const navToggle = document.querySelector(".nav-toggle");
const navLinks = document.querySelectorAll(".nav-links a, .nav-actions a");
const themeToggle = document.getElementById("themeToggle");
const cursorGlow = document.querySelector(".cursor-glow");
const cursorDot = document.querySelector(".cursor-dot");
const loginOpenBtn = document.getElementById("loginOpenBtn");
const authModal = document.getElementById("authModal");
const authLoginTab = document.getElementById("authLoginTab");
const authSignupTab = document.getElementById("authSignupTab");
const loginForm = document.getElementById("loginForm");
const signupForm = document.getElementById("signupForm");
const authMessage = document.getElementById("authMessage");
const profileModal = document.getElementById("profileModal");
const profileInitial = document.getElementById("profileInitial");
const profileName = document.getElementById("profileName");
const profileEmail = document.getElementById("profileEmail");
const profilePlan = document.getElementById("profilePlan");
const profileCredits = document.getElementById("profileCredits");
const profileLogoutBtn = document.getElementById("profileLogoutBtn");
const profileConnectBtn = document.getElementById("profileConnectBtn");
function getAuthToken() {  // returns the current Auth Token value
  return localStorage.getItem(STORAGE_KEYS.authToken) || "";
}
function getAuthUser() {  // returns the current Auth User value
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.authUser) || "null");
  } catch (error) {
    return null;
  }
}
function setAuthMessage(message, type = "") {  // sets the Auth Message value in the UI/state
  if (!authMessage) return;
  authMessage.textContent = message || "";
  authMessage.className = `auth-message ${type}`.trim();
}
function updateAuthUi(user = getAuthUser()) {  // refreshes the Auth UI/state
  if (!loginOpenBtn) return;
  if (user && user.name) {
    loginOpenBtn.textContent = user.name.split(" ")[0] || "Account";
    loginOpenBtn.title = `${user.email} - open profile`;
    loginOpenBtn.dataset.authenticated = "true";
  } else {
    loginOpenBtn.textContent = "Login";
    loginOpenBtn.title = "Sign in or create an account";
    loginOpenBtn.dataset.authenticated = "false";
  }
}
function openAuthModal(tab = "login") {  // opens the login/signup modal in the frontend
  if (!authModal) return;
  authModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  switchAuthTab(tab);
}
function closeAuthModal() {  // closes the login/signup modal in the frontend
  if (!authModal) return;
  authModal.classList.add("hidden");
  document.body.classList.remove("modal-open");
  setAuthMessage("");
}
function fillProfile(user = getAuthUser()) {  // fills profile UI fields from the current auth user
  if (!user) return;
  const name = user.name || "ClipForge User";
  if (profileInitial) profileInitial.textContent = name.trim().charAt(0).toUpperCase() || "C";
  if (profileName) profileName.textContent = name;
  if (profileEmail) profileEmail.textContent = user.email || "";
  if (profilePlan) profilePlan.textContent = user.plan || "Free";
  if (profileCredits) profileCredits.textContent = String(user.credits ?? 30);
}
function openProfileModal() {  // opens the local profile/account modal
  const user = getAuthUser();
  if (!profileModal || !user) {
    openAuthModal("login");
    return;
  }
  fillProfile(user);
  profileModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}
function closeProfileModal() {  // closes the local profile/account modal
  if (!profileModal) return;
  profileModal.classList.add("hidden");
  document.body.classList.remove("modal-open");
}
function switchAuthTab(tab) {  // switches the auth modal between login and signup tabs
  const isSignup = tab === "signup";
  authLoginTab?.classList.toggle("active", !isSignup);
  authSignupTab?.classList.toggle("active", isSignup);
  loginForm?.classList.toggle("hidden", isSignup);
  signupForm?.classList.toggle("hidden", !isSignup);
  setAuthMessage("");
}
function storeAuthSession(data) {  // saves auth token/user data in local browser storage
  localStorage.setItem(STORAGE_KEYS.authToken, data.token);
  localStorage.setItem(STORAGE_KEYS.authUser, JSON.stringify(data.user));
  updateAuthUi(data.user);
}
function authHeaders() {  // builds Authorization headers for authenticated API calls
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
async function submitAuthForm(endpoint, fields) {  // submits login or signup data to the backend auth endpoint
  const formData = new FormData();
  Object.entries(fields).forEach(([key, value]) => formData.append(key, value));
  const data = await fetchJson(`${API_BASE}${endpoint}`, {
    method: "POST",
    body: formData,
  });
  storeAuthSession(data);
  setAuthMessage("Account connected successfully.", "success");
  setTimeout(closeAuthModal, 650);
}
async function logoutUser() {  // logs out locally and clears auth UI state
  try {
    await fetchJson(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: authHeaders(),
    });
  } catch (error) {
    // Local logout should still work if the backend is offline.
  }
  localStorage.removeItem(STORAGE_KEYS.authToken);
  localStorage.removeItem(STORAGE_KEYS.authUser);
  updateAuthUi(null);
}

loginOpenBtn?.addEventListener("click", () => {
  if (loginOpenBtn.dataset.authenticated === "true") {
    openProfileModal();
    return;
  }
  openAuthModal("login");
});

document.querySelectorAll("[data-auth-close]").forEach((el) => {
  el.addEventListener("click", closeAuthModal);
});

document.querySelectorAll("[data-profile-close]").forEach((el) => {
  el.addEventListener("click", closeProfileModal);
});

profileLogoutBtn?.addEventListener("click", async () => {
  await logoutUser();
  closeProfileModal();
});

profileConnectBtn?.addEventListener("click", () => {
  closeProfileModal();
  openAuthModal("login");
  setAuthMessage("Social connection needs OAuth keys on hosting. Email login works now for testing.", "error");
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  closeAuthModal();
  closeProfileModal();
});

authLoginTab?.addEventListener("click", () => switchAuthTab("login"));
authSignupTab?.addEventListener("click", () => switchAuthTab("signup"));

document.querySelectorAll("[data-oauth]").forEach((button) => {
  button.addEventListener("click", () => {
    setAuthMessage(`${button.dataset.oauth} login needs OAuth keys on hosting. Email login works now for testing.`, "error");
  });
});

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setAuthMessage("Signing in...");
    await submitAuthForm("/auth/login", {
      email: document.getElementById("loginEmail").value,
      password: document.getElementById("loginPassword").value,
    });
  } catch (error) {
    setAuthMessage(error.message, "error");
  }
});

signupForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setAuthMessage("Creating account...");
    await submitAuthForm("/auth/signup", {
      name: document.getElementById("signupName").value,
      email: document.getElementById("signupEmail").value,
      password: document.getElementById("signupPassword").value,
    });
  } catch (error) {
    setAuthMessage(error.message, "error");
  }
});

updateAuthUi();

if (navToggle && topNav) {
  navToggle.addEventListener("click", () => {
    const isOpen = topNav.classList.toggle("menu-open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
    navToggle.setAttribute("aria-label", isOpen ? "Close navigation menu" : "Open navigation menu");
  });

  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      topNav.classList.remove("menu-open");
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Open navigation menu");
    });
  });
}


const TIMELINE_STAGES = [
  "Upload / Link Submitted",
  "Job Queued",
  "Transcribing Audio",
  "Detecting Highlights",
  "Rendering Shorts",
  "Creating Captions",
  "Generating Thumbnails",
  "Writing Metadata",
  "Building ZIP Package",
  "Complete",
];

let activeCreatorStep = 1;
let maxUnlockedCreatorStep = 1;
let currentTimelineStage = -1;
let manualRangesState = [];
let manualPreviewObjectUrl = "";
let selectedMusicTrack = "";
let selectedMusicCategory = "";
let musicTrackRequestId = 0;
let selectedProjectInputPath = "";
let selectedProjectInputName = "";
let selectedProjectInputUrl = "";
function labelFromSelect(id) {  // handles label From Select UI behavior
  const el = document.getElementById(id);
  return el?.selectedOptions?.[0]?.textContent?.trim() || getValue(id) || "Not set";
}
function clearProjectInputSelection() {  // clears the Project Input Selection UI/state
  selectedProjectInputPath = "";
  selectedProjectInputName = "";
  selectedProjectInputUrl = "";
  projectInputList?.querySelectorAll("[data-project-input-path]").forEach((button) => button.classList.remove("active"));
}
function selectProjectInputVideo(item) {  // selects one local input-library video for processing
  selectedProjectInputPath = item.relative_path || "";
  selectedProjectInputName = item.name || selectedProjectInputPath;
  selectedProjectInputUrl = item.url || "";
  const fileInput = document.getElementById("videoFile");
  if (fileInput) fileInput.value = "";
  projectInputList?.querySelectorAll("[data-project-input-path]").forEach((button) => {
    button.classList.toggle("active", button.dataset.projectInputPath === selectedProjectInputPath);
  });
  updateInputUnlock();
  updateFlowSummary();
  updateManualPreviewVideo();
  updateCaptionPreviewVideo();
}
function renderProjectInputList(videos = []) {  // renders the render Project Input List section from current app state
  if (!projectInputList) return;
  if (!videos.length) {
    projectInputList.innerHTML = `<p class="project-input-empty">No videos found in this backend project's data/input folder.</p>`;
    return;
  }
  projectInputList.innerHTML = videos.map((item) => `
    <button type="button" class="project-input-item ${item.relative_path === selectedProjectInputPath ? "active" : ""}" data-project-input-path="${escapeHtml(item.relative_path)}">
      <strong>${escapeHtml(item.name)}</strong>
      <span>${escapeHtml(item.folder || "data/input")}</span>
    </button>
  `).join("");
  projectInputList.querySelectorAll("[data-project-input-path]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = videos.find((entry) => entry.relative_path === button.dataset.projectInputPath);
      if (item) selectProjectInputVideo(item);
    });
  });
}
async function loadProjectInputLibrary() {  // loads load Project Input Library data into the browser UI
  if (!projectInputList) return;
  projectInputList.innerHTML = `<p class="project-input-empty">Loading current project data/input videos...</p>`;
  try {
    const response = await fetch(`${API_BASE}/input-library?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Input library failed: ${response.status}`);
    const data = await response.json();
    if (projectInputRoot) projectInputRoot.textContent = data.root ? `Backend folder: ${data.root}` : "Uses this backend project's data/input folder.";
    renderProjectInputList(Array.isArray(data.videos) ? data.videos : []);
  } catch (error) {
    projectInputList.innerHTML = `<p class="project-input-empty error">Could not load backend data/input. Make sure FastAPI is running.</p>`;
  }
}
function hasValidInput() {  // checks whether upload, link, or local input is ready to submit
  if (mode === "upload") {
    return Boolean(selectedProjectInputPath || document.getElementById("videoFile")?.files?.length);
  }
  const value = getValue("videoUrl").trim();
  return value.length > 6 && /^(https?:\/\/|www\.|[a-z0-9-]+\.)/i.test(value);
}
function setCreatorStep(step) {  // sets the Creator Step value in the UI/state
  const cleanStep = Math.max(1, Math.min(5, Number(step) || 1));
  if (cleanStep > maxUnlockedCreatorStep) return;
  activeCreatorStep = cleanStep;

  creatorSteps.forEach((button) => {
    const stepNo = Number(button.dataset.step);
    button.classList.toggle("active", stepNo === activeCreatorStep);
    button.classList.toggle("completed", stepNo < maxUnlockedCreatorStep);
    button.classList.toggle("step-active", stepNo === activeCreatorStep);
    button.classList.toggle("step-completed", stepNo < maxUnlockedCreatorStep);
    button.classList.toggle("locked", stepNo > maxUnlockedCreatorStep);
    const mark = button.querySelector(".step-mark");
    if (mark) mark.textContent = stepNo < maxUnlockedCreatorStep ? "?" : String(stepNo);
  });

  creatorStepPanels.forEach((panel) => {
    panel.classList.toggle("active", Number(panel.dataset.stepPanel) === activeCreatorStep);
  });

  updateFlowConditionals();
  updateFlowSummary();
}
function unlockCreatorStep(step) {  // enables the next Creator Studio step after required input is valid
  maxUnlockedCreatorStep = Math.max(maxUnlockedCreatorStep, Number(step) || 1);
  setCreatorStep(Math.min(Number(step) || activeCreatorStep, maxUnlockedCreatorStep));
}
function updateInputUnlock() {  // refreshes the Input Unlock UI/state
  const nextBtn = document.querySelector('[data-step-panel="1"] [data-next-step="2"]');
  if (nextBtn) nextBtn.disabled = !hasValidInput();
  if (hasValidInput()) maxUnlockedCreatorStep = Math.max(maxUnlockedCreatorStep, 2);
  setCreatorStep(activeCreatorStep);
}
function getCaptionPreset(value = getValue("fontPreset")) {  // returns the current Caption Preset value
  return CAPTION_PRESETS.find((preset) => preset.value === value) || CAPTION_PRESETS[0];
}
function getResolvedCaptionCase(preset = getCaptionPreset()) {  // returns the current Resolved Caption Case value
  const selectedCase = getValue("captionCase") || "preset";
  return selectedCase === "preset" ? (preset.textCase || "normal") : selectedCase;
}
function applyCaptionCase(text, resolvedCase) {  // applies uppercase/title/normal casing to caption preview text
  if (resolvedCase === "uppercase") return String(text || "").toUpperCase();
  if (resolvedCase === "lowercase") return String(text || "").toLowerCase();
  return String(text || "");
}
function labelTextFromValue(value) {  // turns an option value into readable UI label text
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
function getEditingWorkflow() {  // returns the current Editing Workflow value
  return getValue("editingWorkflow") || "";
}
function getEffectiveEditingStyle() {  // returns the current Effective Editing Style value
  return getEditingWorkflow() === "style" && getValue("editingStyle") ? getValue("editingStyle") : "none";
}
function setSelectValue(id, value) {  // sets the Select Value value in the UI/state
  const el = document.getElementById(id);
  if (!el || value === undefined || value === null) return;
  el.value = String(value);
}
function applyEditingStylePreset() {  // applies a smart editing preset to caption/reframe/filter controls
  if (getEditingWorkflow() !== "style" || !getValue("editingStyle")) return;
  const preset = EDITING_STYLE_PRESETS[getValue("editingStyle")] || EDITING_STYLE_PRESETS.podcast;
  setSelectValue("captions", "true");
  setSelectValue("captionSize", preset.captionSize);
  setSelectValue("captionPosition", preset.captionPosition);
  setSelectValue("fontPreset", preset.fontPreset);
  setSelectValue("fontFamily", preset.fontFamily);
  setSelectValue("captionCase", preset.captionCase);
  setSelectValue("filterPreset", preset.filter);
  setSelectValue("musicEnabled", preset.musicEnabled ? "true" : "false");
  setSelectValue("musicCategory", preset.musicCategory);
  setSelectValue("musicVolume", preset.musicVolume);
  setSelectValue("reframe", preset.reframe);
}
function updateStyleAppliedSummary() {  // refreshes the Style Applied Summary UI/state
  const box = document.getElementById("styleAppliedSummary");
  if (!box) return;

  if (!getEditingWorkflow()) {
    box.innerHTML = "";
    return;
  }

  if (getEditingWorkflow() === "custom") {
    box.innerHTML = `<strong>Custom editing selected</strong><span>All caption, filter, and music controls are unlocked below.</span>`;
    return;
  }

  if (!getValue("editingStyle")) {
    box.innerHTML = `<strong>Smart style selected</strong><span>Choose one content style to auto-fill captions, filter, and music.</span>`;
    return;
  }

  const preset = EDITING_STYLE_PRESETS[getValue("editingStyle")] || EDITING_STYLE_PRESETS.podcast;
  const musicText = preset.musicEnabled ? `${labelFromSelect("musicCategory")} at ${Math.round(Number(getValue("musicVolume") || 0) * 100)}%` : "Music off";
  box.innerHTML = `
    <strong>${escapeHtml(preset.name)} applied</strong>
    <span>Filter: ${escapeHtml(labelFromSelect("filterPreset"))}</span>
    <span>Captions: ${escapeHtml(labelFromSelect("fontPreset"))}, ${escapeHtml(labelFromSelect("captionSize"))}, ${escapeHtml(labelFromSelect("captionPosition"))}</span>
    <span>Music: ${escapeHtml(musicText)}</span>
  `;
}
function updateEditingWorkflowUi() {  // refreshes the Editing Workflow UI/state
  const workflow = getEditingWorkflow();
  const isCustom = workflow === "custom";
  const isStyle = workflow === "style";
  const hasStyle = isStyle && Boolean(getValue("editingStyle"));
  const hasChoice = isCustom || hasStyle;

  document.querySelectorAll("[data-editing-workflow]").forEach((button) => {
    button.classList.toggle("active", button.dataset.editingWorkflow === workflow);
  });

  document.querySelectorAll(".editing-dependent").forEach((item) => {
    item.classList.toggle("setup-hidden", !workflow || (isStyle && !hasStyle && !item.classList.contains("style-editing-option") && !item.classList.contains("style-applied-summary")));
  });

  document.querySelectorAll(".style-editing-option").forEach((item) => item.classList.toggle("reveal", isStyle));
  document.querySelectorAll(".custom-editing-option").forEach((item) => item.classList.toggle("style-hidden", isStyle && !item.classList.contains("music-preview-card")));

  if (hasStyle) applyEditingStylePreset();
  updateStyleAppliedSummary();
  updateMusicPreview();

  const nextBtn = document.getElementById("styleContinueBtn") || document.querySelector('[data-step-panel="3"] [data-next-step="4"]');
  if (nextBtn) nextBtn.disabled = !hasChoice;
}
function renderCaptionPresetGrid() {  // renders the render Caption Preset Grid section from current app state
  if (!captionPresetGrid) return;
  captionPresetGrid.innerHTML = CAPTION_PRESETS.map((preset) => `
    <button class="caption-preset-card preset-${preset.value}" type="button" data-caption-preset="${preset.value}">
      <span class="preset-mini-preview">
        <span>${escapeHtml(preset.sampleA)}</span>
        <strong>${escapeHtml(preset.sampleB)}</strong>
      </span>
      <small>${escapeHtml(preset.name)}</small>
    </button>
  `).join("");

  captionPresetGrid.querySelectorAll("[data-caption-preset]").forEach((button) => {
    button.addEventListener("click", () => {
      const select = document.getElementById("fontPreset");
      if (select) {
        select.value = button.dataset.captionPreset || "clean_white";
        const familySelect = document.getElementById("fontFamily");
        if (familySelect) familySelect.value = "preset";
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  });
}
function syncMusicVolumeUi() {  // updates the visible music-volume label from the slider value
  const volume = Math.max(0, Math.min(1, Number(getValue("musicVolume") || 0)));
  if (musicVolumeValue) musicVolumeValue.textContent = `${Math.round(volume * 100)}%`;
  if (musicPreviewAudio) musicPreviewAudio.volume = volume;
}
function clearMusicTrackList(message = "") {  // clears the Music Track List UI/state
  if (musicTrackList) musicTrackList.innerHTML = "";
  selectedMusicTrack = "";
  selectedMusicCategory = "";
  if (message && musicPreviewStatus) musicPreviewStatus.textContent = message;
}
function setMusicPreviewSource(category, trackName) {  // sets the Music Preview Source value in the UI/state
  if (!musicPreviewAudio || !trackName) return;
  const encodedTrackPath = String(trackName).split("/").map(encodeURIComponent).join("/");
  const nextSrc = `${API_BASE}/music/preview/${encodeURIComponent(category)}/${encodedTrackPath}?v=${Date.now()}`;
  musicPreviewAudio.classList.remove("hidden-audio-preview");
  if (musicPreviewAudio.src !== nextSrc) {
    musicPreviewAudio.src = nextSrc;
    musicPreviewAudio.load?.();
  }
  if (musicPreviewStatus) musicPreviewStatus.textContent = `Previewing ${trackName.replace(/\.[^.]+$/, "")} (${labelFromSelect("musicCategory")}).`;
}
function renderMusicTrackList(category, tracks) {  // renders the render Music Track List section from current app state
  if (!musicTrackList) return;
  if (!tracks.length) {
    musicTrackList.innerHTML = `<span class="music-track-empty">No tracks found in this category.</span>`;
    return;
  }

  musicTrackList.innerHTML = tracks.map((track, index) => {
    const isActive = track.name === selectedMusicTrack;
    return `<button class="music-track-btn ${isActive ? "active" : ""}" type="button" data-track-name="${escapeHtml(track.name)}"><span>${index + 1}</span>${escapeHtml(track.label || track.name)}</button>`;
  }).join("");

  musicTrackList.querySelectorAll("[data-track-name]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedMusicCategory = category;
      selectedMusicTrack = button.dataset.trackName || "";
      musicTrackList.querySelectorAll(".music-track-btn").forEach((item) => item.classList.toggle("active", item === button));
      setMusicPreviewSource(category, selectedMusicTrack);
    });
  });
}
async function updateMusicPreview() {  // refreshes the Music Preview UI/state
  syncMusicVolumeUi();
  if (!musicPreviewAudio || !musicPreviewStatus) return;

  const musicOn = getValue("musicEnabled") === "true";
  const category = getValue("musicCategory") || "none";

  if (!musicOn) {
    musicPreviewAudio.removeAttribute("src");
    musicPreviewAudio.load?.();
    musicPreviewAudio.classList.add("hidden-audio-preview");
    clearMusicTrackList("Music is off for this package.");
    return;
  }

  if (category === "none") {
    musicPreviewAudio.removeAttribute("src");
    musicPreviewAudio.load?.();
    musicPreviewAudio.classList.add("hidden-audio-preview");
    clearMusicTrackList("Choose a category to preview tracks.");
    return;
  }

  if (category === "auto") {
    musicPreviewAudio.removeAttribute("src");
    musicPreviewAudio.load?.();
    musicPreviewAudio.classList.add("hidden-audio-preview");
    clearMusicTrackList("AI Auto will choose the best music after transcription.");
    return;
  }

  const requestId = ++musicTrackRequestId;
  if (selectedMusicCategory !== category) {
    selectedMusicCategory = category;
    selectedMusicTrack = "";
  }
  musicPreviewStatus.textContent = `Loading ${labelFromSelect("musicCategory")} tracks...`;

  try {
    const response = await fetch(`${API_BASE}/music/tracks/${encodeURIComponent(category)}?v=${Date.now()}`);
    if (!response.ok) throw new Error("No tracks found");
    const data = await response.json();
    if (requestId !== musicTrackRequestId) return;
    const tracks = Array.isArray(data.tracks) ? data.tracks : [];
    if (!tracks.length) {
      musicPreviewAudio.removeAttribute("src");
      musicPreviewAudio.load?.();
      musicPreviewAudio.classList.add("hidden-audio-preview");
      renderMusicTrackList(category, []);
      musicPreviewStatus.textContent = `No ${labelFromSelect("musicCategory")} tracks found.`;
      return;
    }

    if (!tracks.some((track) => track.name === selectedMusicTrack)) {
      selectedMusicTrack = tracks[0].name;
    }
    renderMusicTrackList(category, tracks);
    setMusicPreviewSource(category, selectedMusicTrack);
  } catch (error) {
    if (requestId !== musicTrackRequestId) return;
    musicPreviewAudio.removeAttribute("src");
    musicPreviewAudio.load?.();
    musicPreviewAudio.classList.add("hidden-audio-preview");
    renderMusicTrackList(category, []);
    musicPreviewStatus.textContent = "No preview track found for this category.";
  }
}
function updateCaptionPreviewVideo() {  // refreshes the Caption Preview Video UI/state
  if (!captionPreviewVideo) return;
  const file = document.getElementById("videoFile")?.files?.[0];
  if (captionPreviewVideo.dataset.objectUrl) {
    URL.revokeObjectURL(captionPreviewVideo.dataset.objectUrl);
    captionPreviewVideo.dataset.objectUrl = "";
  }
  if (selectedProjectInputUrl && !file) {
    captionPreviewVideo.src = makeApiUrl(selectedProjectInputUrl);
    captionPreviewVideo.classList.add("has-video");
    captionPreviewVideo.currentTime = 0;
    captionPreviewVideo.play?.().catch(() => {});
    return;
  }
  if (!file) {
    captionPreviewVideo.removeAttribute("src");
    captionPreviewVideo.classList.remove("has-video");
    captionPreviewVideo.load?.();
    return;
  }
  const objectUrl = URL.createObjectURL(file);
  captionPreviewVideo.dataset.objectUrl = objectUrl;
  captionPreviewVideo.src = objectUrl;
  captionPreviewVideo.classList.add("has-video");
  captionPreviewVideo.currentTime = 0;
  captionPreviewVideo.play?.().catch(() => {});
}
function updateCaptionPreview() {  // refreshes the Caption Preview UI/state
  const captionsOn = getValue("captions") !== "false";
  const preset = getCaptionPreset();
  const size = getValue("captionSize") || "medium";
  const position = getValue("captionPosition") || "bottom_center";
  const familyValue = getValue("fontFamily") || "preset";
  const family = familyValue === "preset" ? preset.family : familyValue;
  const resolvedCase = getResolvedCaptionCase(preset);
  const musicOn = getValue("musicEnabled") === "true";
  const musicVolume = Math.max(0, Math.min(1, Number(getValue("musicVolume") || 0)));
  const filterSlug = labelTextFromValue(getValue("filterPreset")).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "none";

  document.querySelectorAll("[data-caption-preset]").forEach((button) => {
    button.classList.toggle("active", button.dataset.captionPreset === preset.value);
  });

  if (captionPreviewFrame) {
    captionPreviewFrame.className = `preview-video-frame preview-filter-${filterSlug} ${musicOn ? "preview-music-on" : "preview-music-off"}`;
  }

  if (captionPreviewVideo) {
    captionPreviewVideo.volume = 0;
    captionPreviewVideo.muted = true;
  }

  if (captionPreviewText) {
    captionPreviewText.className = `preview-caption preview-style-${preset.value} preview-size-${size} preview-pos-${position} preview-case-${resolvedCase}`;
    const renderFontSize = CAPTION_RENDER_SIZES[size] || CAPTION_RENDER_SIZES.medium;
    captionPreviewText.style.setProperty("font-size", `${Math.round(renderFontSize * 0.4)}px`, "important");
    captionPreviewText.style.fontFamily = `${family}, Arial, sans-serif`;
    captionPreviewText.innerHTML = `<span>${escapeHtml(applyCaptionCase(preset.sampleA, resolvedCase))}</span><strong>${escapeHtml(applyCaptionCase(preset.sampleB, resolvedCase))}</strong>`;
    captionPreviewText.classList.toggle("is-off", !captionsOn);
  }

  if (captionPreviewName) captionPreviewName.textContent = captionsOn ? preset.name : "Captions Off";
  if (captionPreviewDetails) {
    captionPreviewDetails.textContent = captionsOn
      ? `${family} - ${labelTextFromValue(size)} - ${labelTextFromValue(position)} - ${labelTextFromValue(resolvedCase)}`
      : "Preview hidden when captions are off";
  }

  if (captionPreviewStyleState) {
    const styleLabel = getEffectiveEditingStyle() === "none" ? "Custom editing" : labelFromSelect("editingStyle");
    const trackLabel = musicOn && selectedMusicCategory === getValue("musicCategory") && selectedMusicTrack
      ? `, ${selectedMusicTrack.replace(/\.[^.]+$/, "")}` 
      : "";
    const musicLabel = musicOn ? `${labelFromSelect("musicCategory")} music, ${Math.round(musicVolume * 100)}%${trackLabel}` : "Music off";
    captionPreviewStyleState.textContent = `${styleLabel} - ${labelFromSelect("filterPreset")} - ${musicLabel}`;
  }
}
function setupCaptionStylePreview() {  // sets the up Caption Style Preview value in the UI/state
  renderCaptionPresetGrid();
  updateCaptionPreview();
}
function updateFlowConditionals() {  // refreshes the Flow Conditionals UI/state
  const segmentMode = getValue("segmentMode");
  const isStyleMode = getEditingWorkflow() === "style";

  document.querySelectorAll(".mode-extra").forEach((item) => {
    item.classList.toggle("reveal", item.dataset.modeExtra === segmentMode);
  });

  updateEditingWorkflowUi();

  const captionsOn = getValue("captions") !== "false";
  document.querySelectorAll(".caption-option").forEach((item) => {
    const isCustomOnly = item.classList.contains("custom-editing-option");
    item.classList.toggle("reveal", captionsOn && (!isCustomOnly || !isStyleMode));
  });

  const musicOn = getValue("musicEnabled") === "true";
  document.querySelectorAll(".music-option").forEach((item) => {
    const isPreviewCard = item.classList.contains("music-preview-card");
    item.classList.toggle("reveal", musicOn && (!isStyleMode || isPreviewCard));
  });
}
function inputSummaryText() {  // builds the package summary text for selected upload/link/local input
  if (mode === "upload") {
    if (selectedProjectInputPath) return `Project input: ${selectedProjectInputName || selectedProjectInputPath}`;
    const count = document.getElementById("videoFile")?.files?.length || 0;
    if (!count) return "No file selected";
    return count === 1 ? "1 video selected" : `${count} videos selected`;
  }
  return getValue("videoUrl").trim() || "No link pasted";
}
function getFlowSummaryHtml() {  // returns the current Flow Summary Html value
  const captionsOn = getValue("captions") !== "false";
  const musicOn = getValue("musicEnabled") === "true";
  return `
    <div class="summary-head"><strong>Package Summary</strong><span>${mode === "upload" ? "Upload" : "Link"}</span></div>
    <div class="summary-grid">
      <span>Input</span><strong>${escapeHtml(inputSummaryText())}</strong>
      <span>Segment</span><strong>${escapeHtml(labelFromSelect("segmentMode"))}</strong>
      <span>Aspect</span><strong>${escapeHtml(labelFromSelect("aspectRatio"))}</strong>
      <span>Editing</span><strong>${escapeHtml(getEffectiveEditingStyle() === "none" ? "Custom Editing" : labelFromSelect("editingStyle"))}</strong>
      <span>Quality</span><strong>${escapeHtml(labelFromSelect("outputResolution"))}</strong>
      <span>Captions</span><strong>${captionsOn ? "On" : "Off"}</strong>
      <span>Music</span><strong>${musicOn ? labelFromSelect("musicCategory") : "Off"}</strong>
      ${getValue("segmentMode") === "manual" ? `<span>Manual Clips</span><strong>${manualRangesState.length || "None"}</strong>` : ""}
    </div>
    <p>Expected outputs: shorts, thumbnails, metadata, and ZIP package.</p>
  `;
}
function updateFlowSummary() {  // refreshes the Flow Summary UI/state
  const html = getFlowSummaryHtml();
  if (flowSummaryCard) flowSummaryCard.innerHTML = html;
  if (finalSummaryCard) finalSummaryCard.innerHTML = html;
}
function renderTimeline(activeIndex = -1, failed = false) {  // renders the render Timeline section from current app state
  if (!processingTimeline) return;
  currentTimelineStage = activeIndex;
  processingTimeline.innerHTML = TIMELINE_STAGES.map((label, index) => {
    const state = failed && index === activeIndex ? "failed" : index < activeIndex ? "done" : index === activeIndex ? "active" : "pending";
    const mark = state === "done" ? "\u2713" : state === "failed" ? "!" : String(index + 1);
    return `<li class="${state}"><span>${mark}</span><strong>${label}</strong></li>`;
  }).join("");
}
function setTimelineForStatus(statusOrJob) {  // sets the Timeline For Status value in the UI/state
  const job = typeof statusOrJob === "object" && statusOrJob ? statusOrJob : null;
  const status = job ? job.status : statusOrJob;
  const backendStage = job && Number.isFinite(Number(job.progress_stage))
    ? Number(job.progress_stage)
    : null;
  const failed = status === "failed" || Boolean(job?.progress_failed);

  let stage = backendStage;

  if (stage === null) {
    if (status === "queued") stage = 1;
    else if (status === "processing") stage = Math.max(currentTimelineStage, 2);
    else if (status === "completed") stage = TIMELINE_STAGES.length;
    else if (status === "failed") stage = Math.max(currentTimelineStage, 1);
    else stage = Math.max(currentTimelineStage, 0);
  }

  if (status === "completed") {
    renderTimeline(TIMELINE_STAGES.length);
    return;
  }

  renderTimeline(Math.max(-1, Math.min(TIMELINE_STAGES.length - 1, stage)), failed);
}
function getBackendStage(job, fallbackStage = 0) {  // returns the current Backend Stage value
  return Number.isFinite(Number(job?.progress_stage)) ? Number(job.progress_stage) : fallbackStage;
}
function getBackendStageLabel(job, fallbackLabel = "Processing") {  // returns the current Backend Stage Label value
  return job?.progress_label || TIMELINE_STAGES[Math.min(getBackendStage(job), TIMELINE_STAGES.length - 1)] || fallbackLabel;
}
function setProgressForJob(job, fallbackStage = 0, fallbackLabel = "Processing") {  // sets the Progress For Job value in the UI/state
  const stage = getBackendStage(job, fallbackStage);
  const percent = Number.isFinite(Number(job?.progress_percent))
    ? Number(job.progress_percent)
    : Math.max(0, Math.min(100, Math.round((stage / TIMELINE_STAGES.length) * 100)));
  setProgress(percent, getBackendStageLabel(job, fallbackLabel));
}
function parseManualTime(value) {  // converts manual range time text into seconds
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return NaN;

  const minSecMatch = raw.match(/^(?:(\d+(?:\.\d+)?)m)?\s*(?:(\d+(?:\.\d+)?)s)?$/);
  if (minSecMatch && (minSecMatch[1] || minSecMatch[2])) {
    return (Number(minSecMatch[1] || 0) * 60) + Number(minSecMatch[2] || 0);
  }

  if (/^\d+(?:\.\d+)?$/.test(raw)) return Number(raw);

  const parts = raw.split(":").map((part) => part.trim());
  if (!parts.length || parts.length > 3 || parts.some((part) => part === "" || Number.isNaN(Number(part)))) {
    return NaN;
  }

  const nums = parts.map(Number);
  if (nums.length === 2) return nums[0] * 60 + nums[1];
  if (nums.length === 3) return nums[0] * 3600 + nums[1] * 60 + nums[2];
  return NaN;
}
function formatManualTime(seconds) {  // formats seconds into manual range time text
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(secs).padStart(2, "0");
  return hours > 0 ? `${String(hours).padStart(2, "0")}:${mm}:${ss}` : `${mm}:${ss}`;
}
function setManualMessage(message, type = "") {  // sets the Manual Message value in the UI/state
  const el = document.getElementById("manualRangeMessage");
  if (!el) return;
  el.textContent = message;
  el.className = `manual-range-message ${type}`.trim();
}
function syncManualRangesInput() {  // writes the manual range builder state into the hidden form value
  const input = document.getElementById("manualRanges");
  if (input) {
    input.value = manualRangesState
      .map((range) => `${formatManualTime(range.start)}-${formatManualTime(range.end)}`)
      .join(";");
  }

  const count = document.getElementById("manualRangeCount");
  if (count) count.textContent = `${manualRangesState.length} clip${manualRangesState.length === 1 ? "" : "s"}`;
}
function renderManualRanges() {  // renders the render Manual Ranges section from current app state
  syncManualRangesInput();
  const list = document.getElementById("manualRangeList");
  if (!list) return;

  if (!manualRangesState.length) {
    list.innerHTML = `<p class="manual-empty">No manual clips added yet.</p>`;
    return;
  }

  list.innerHTML = manualRangesState.map((range, index) => {
    const duration = range.end - range.start;
    return `
      <article class="manual-range-chip">
        <span>${index + 1}</span>
        <strong>${formatManualTime(range.start)} - ${formatManualTime(range.end)}</strong>
        <small>${Math.round(duration)} sec</small>
        <button type="button" data-manual-edit="${index}">Edit</button>
        <button type="button" data-manual-delete="${index}">Delete</button>
      </article>
    `;
  }).join("");
}
function getManualVideoDuration() {  // returns the current Manual Video Duration value
  const preview = document.getElementById("manualPreviewVideo");
  return Number.isFinite(preview?.duration) ? preview.duration : 0;
}
function addManualRange() {  // adds one validated manual clip range to the builder
  const startInput = document.getElementById("manualStartTime");
  const endInput = document.getElementById("manualEndTime");
  const start = parseManualTime(startInput?.value);
  const end = parseManualTime(endInput?.value);
  const duration = getManualVideoDuration();

  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    setManualMessage("Add valid start and end times, for example 00:10 and 00:45.", "error");
    return;
  }

  if (end <= start) {
    setManualMessage("End time must be after start time.", "error");
    return;
  }

  if (end - start < 5) {
    setManualMessage("Clip should be at least 5 seconds long.", "error");
    return;
  }

  if (duration && end > duration + 1) {
    setManualMessage(`End time is outside the selected video duration (${formatManualTime(duration)}).`, "error");
    return;
  }

  const overlaps = manualRangesState.some((range) => start < range.end && end > range.start);
  manualRangesState.push({ start, end });
  manualRangesState.sort((a, b) => a.start - b.start);
  startInput.value = "";
  endInput.value = "";
  renderManualRanges();
  updateFlowSummary();
  setManualMessage(overlaps ? "Clip added. Note: it overlaps another range." : "Clip added. Backend range format updated.", overlaps ? "warn" : "success");
}
function setManualInputFromPreview(inputId) {  // sets the Manual Input From Preview value in the UI/state
  const preview = document.getElementById("manualPreviewVideo");
  const input = document.getElementById(inputId);
  if (!preview || !input || !Number.isFinite(preview.currentTime)) return;
  input.value = formatManualTime(preview.currentTime);
  setManualMessage("Current playback time added.", "success");
}
function updateManualPreviewVideo() {  // refreshes the Manual Preview Video UI/state
  const preview = document.getElementById("manualPreviewVideo");
  const hint = document.getElementById("manualPreviewHint");
  const fileInput = document.getElementById("videoFile");
  if (!preview || !fileInput) return;

  if (manualPreviewObjectUrl) {
    URL.revokeObjectURL(manualPreviewObjectUrl);
    manualPreviewObjectUrl = "";
  }

  const file = fileInput.files?.[0];
  if (selectedProjectInputUrl && !file) {
    preview.src = makeApiUrl(selectedProjectInputUrl);
    preview.load();
    if (hint) hint.textContent = "Project input video selected. Play it, then use current time for start and end points.";
    return;
  }
  if (!file) {
    preview.removeAttribute("src");
    preview.load();
    if (hint) hint.textContent = "Select an uploaded video or project input video to use current playback time.";
    return;
  }

  manualPreviewObjectUrl = URL.createObjectURL(file);
  preview.src = manualPreviewObjectUrl;
  if (hint) hint.textContent = "Play the video, then use current time for start and end points.";
}
function setupManualRangeBuilder() {  // sets the up Manual Range Builder value in the UI/state
  renderManualRanges();
  updateManualPreviewVideo();

  document.getElementById("addManualRangeBtn")?.addEventListener("click", addManualRange);
  document.getElementById("clearManualRangesBtn")?.addEventListener("click", () => {
    manualRangesState = [];
    renderManualRanges();
    updateFlowSummary();
    setManualMessage("Manual clips cleared.", "");
  });
  document.getElementById("setManualStartBtn")?.addEventListener("click", () => setManualInputFromPreview("manualStartTime"));
  document.getElementById("setManualEndBtn")?.addEventListener("click", () => setManualInputFromPreview("manualEndTime"));

  document.getElementById("manualRangeList")?.addEventListener("click", (event) => {
    const editButton = event.target.closest("[data-manual-edit]");
    const deleteButton = event.target.closest("[data-manual-delete]");

    if (editButton) {
      const index = Number(editButton.dataset.manualEdit);
      const range = manualRangesState[index];
      if (!range) return;
      document.getElementById("manualStartTime").value = formatManualTime(range.start);
      document.getElementById("manualEndTime").value = formatManualTime(range.end);
      manualRangesState.splice(index, 1);
      renderManualRanges();
      updateFlowSummary();
      setManualMessage("Range loaded for editing. Adjust and add it again.", "warn");
    }

    if (deleteButton) {
      const index = Number(deleteButton.dataset.manualDelete);
      manualRangesState.splice(index, 1);
      renderManualRanges();
      updateFlowSummary();
      setManualMessage("Range deleted.", "");
    }
  });
}
function setupCreatorFlow() {  // sets the up Creator Flow value in the UI/state
  renderTimeline(-1);
  updateInputUnlock();
  updateFlowConditionals();
  updateFlowSummary();
  setupManualRangeBuilder();
loadProjectInputLibrary();
  setupCaptionStylePreview();

  creatorSteps.forEach((button) => {
    button.addEventListener("click", () => setCreatorStep(Number(button.dataset.step)));
  });

  document.querySelectorAll("[data-editing-workflow]").forEach((button) => {
    button.addEventListener("click", () => {
      const select = document.getElementById("editingWorkflow");
      if (select) {
        select.value = button.dataset.editingWorkflow || "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  });
  document.querySelectorAll("[data-next-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = Number(button.dataset.nextStep);
      if (next === 2 && !hasValidInput()) return;
      unlockCreatorStep(next);
    });
  });

  document.querySelectorAll("[data-prev-step]").forEach((button) => {
    button.addEventListener("click", () => setCreatorStep(Number(button.dataset.prevStep)));
  });

  document.getElementById("videoFile")?.addEventListener("change", () => {
    clearProjectInputSelection();
    updateInputUnlock();
    updateFlowSummary();
    updateManualPreviewVideo();
    updateCaptionPreviewVideo();
  });
  document.getElementById("videoUrl")?.addEventListener("input", updateInputUnlock);

  ["segmentMode", "aspectRatio", "outputResolution", "editingWorkflow", "editingStyle", "captions", "captionSize", "captionPosition", "fontPreset", "fontFamily", "captionCase", "reframe", "filterPreset", "musicEnabled", "musicCategory", "musicVolume"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", () => {
      updateFlowConditionals();
      updateFlowSummary();
      updateCaptionPreview();
    });
    document.getElementById(id)?.addEventListener("input", () => {
      updateFlowSummary();
      updateCaptionPreview();
    });
  });
}

window.startCreatorFlow = function startCreatorFlow(preferredMode = "upload") {
  switchMode(preferredMode === "link" ? "link" : "upload");
  setCreatorStep(1);
  setTimeout(() => {
    document.getElementById(preferredMode === "link" ? "videoUrl" : "videoFile")?.focus();
  }, 350);
};
function getValue(id) {  // returns the current Value value
  const el = document.getElementById(id);
  return el ? el.value : "";
}
function formatDuration(seconds) {  // formats seconds into a readable duration label
  const safe = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(secs).padStart(2, "0");
  return hours > 0 ? `${String(hours).padStart(2, "0")}:${mm}:${ss}` : `${mm}:${ss}`;
}
function resetProgressEvents() {  // clears the visible progress event list for a new job
  seenProgressEvents = new Set();
  renderedProgressEvents = new Map();
  progressEventCounter = 0;
  if (progressEvents) progressEvents.innerHTML = "";
  if (progressEventsCount) progressEventsCount.textContent = "Waiting";
}
function progressEventElapsedLabel(eventTime = null) {  // formats the event stopwatch time from the job start
  const base = jobStartTimestamp || (eventTime ? Date.parse(eventTime) : 0);
  if (!base) return "00:00";
  const endMs = eventTime ? Date.parse(eventTime) : Date.now();
  return formatDuration(Math.max(0, (endMs - base) / 1000));
}
function formatLiveEventDuration(startMs) {  // formats a live event row duration from its own start time
  const safeStart = Number(startMs) || Date.now();
  return formatDuration(Math.max(0, (Date.now() - safeStart) / 1000));
}
function hideTechnicalProgressLine(raw) {  // hides backend/debug lines that are not useful progress events
  const text = String(raw || "").trim();
  const lower = text.toLowerCase();
  if (!text) return true;
  if (/^[=\-_*\s]{8,}$/.test(text)) return true;
  return [
    "loaded model=",
    "processing:",
    "input videos:",
    "captions:",
    "filters:",
    "ffmpeg quality:",
    "plan:",
    "run summary",
    "clip mode:",
    "meta style:",
    "canvas:",
    "models:",
    "whisper transcribing",
  ].some((token) => lower.startsWith(token) || lower.includes(token));
}
function parseLocalStagePercent(raw, percent = null) {  // extracts stage-local percent from transcription text instead of global job percent
  const values = Array.from(String(raw || "").matchAll(/(?:Transcribing|Translating):\s*(\d+(?:\.\d+)?)(?:%|\/100)/gi)).map((match) => Number(match[1]));
  if (values.length) return Math.max(0, Math.min(100, values[values.length - 1]));
  const globalPct = Number(percent);
  if (Number.isFinite(globalPct) && globalPct >= 20 && globalPct <= 30) return Math.max(0, Math.min(100, (globalPct - 20) * 10));
  return null;
}
function normalizeProgressEvent(message, percent = null, stage = null) {  // converts raw backend logs into clean workflow event rows
  const raw = String(message || "").replace(/\r/g, "").trim();
  const lower = raw.toLowerCase();
  if (!raw || hideTechnicalProgressLine(raw)) return null;

  if (lower.includes("started at")) {
    return { key: "job-started", message: raw.replace(/\s+/g, " "), stagePercent: null, live: false, started: true };
  }
  if (lower.includes("job complete") || lower.includes("completed at")) {
    return { key: "job-complete", message: raw.replace(/^Job complete$/i, "Complete"), stagePercent: null, live: false, complete: true };
  }
  if (lower.includes("transcribing:") || lower.includes("translating:")) {
    const stagePercent = parseLocalStagePercent(raw, percent);
    return { key: "stage-transcribing", message: "Transcribing audio", stagePercent, live: true };
  }
  if (lower.includes("audio extracting") || lower.includes("audio: extracting")) {
    return { key: "stage-audio", message: "Extracting audio", stagePercent: null, live: true };
  }
  if (lower.includes("language detected")) {
    const lang = raw.split(":").pop()?.trim();
    return { key: "stage-language", message: lang ? `Detected language: ${lang}` : "Detected language", stagePercent: null, live: false };
  }
  if (lower.includes("highlights selecting segments") || lower.includes("selecting segments") || lower.startsWith("[semantic-ai]")) {
    return { key: "stage-selecting", message: "Selecting best clips", stagePercent: null, live: true };
  }
  if (lower.includes("segments selected")) {
    const count = raw.match(/segments selected:\s*(\d+)/i)?.[1];
    return { key: "stage-selected", message: count ? `Selected ${count} clips` : "Selected clips", stagePercent: null, live: false };
  }
  if (lower.includes("start short")) {
    const match = raw.match(/start short\s+(\d+)\/(\d+)/i);
    return { key: "stage-render", message: match ? `Rendering short ${match[1]}/${match[2]}` : "Rendering short", stagePercent: null, live: true };
  }
  if (lower.includes("building captions track") || lower.includes("burning subtitles")) {
    return { key: "stage-captions", message: "Creating captions", stagePercent: null, live: true };
  }
  if (lower.includes("thumbnail created")) {
    return { key: "stage-thumbnail", message: "Generated thumbnails", stagePercent: null, live: false };
  }
  if (lower.includes("thumbnail") || lower.includes("image generator")) {
    return { key: "stage-thumbnail", message: "Generating thumbnails", stagePercent: null, live: true };
  }
  if (lower.includes("romanizing meta") || lower.includes("report saved") || lower.startsWith("[meta-")) {
    return { key: "stage-metadata", message: "Writing metadata", stagePercent: null, live: true };
  }
  if (lower.includes("adding background music") || lower.includes("adding music")) {
    return { key: "stage-music", message: "Adding music", stagePercent: null, live: true };
  }
  if (lower.includes("completed short")) {
    const match = raw.match(/completed short\s+(\d+)\/(\d+)/i);
    return { key: "stage-render-complete", message: match ? `Completed short ${match[1]}/${match[2]}` : "Completed short", stagePercent: null, live: false };
  }
  if (lower.includes("zip")) {
    return { key: "stage-zip", message: "Building ZIP package", stagePercent: null, live: true };
  }
  if (lower.startsWith("[stage]")) {
    return { key: `stage-${stage || "work"}`, message: raw.replace(/^\[stage\]\s*/i, "").replace(/\.\.\.$/, ""), stagePercent: null, live: true };
  }
  return null;
}
function freezeLiveProgressRows(exceptKey = null) {  // freezes older active rows when a new workflow stage starts
  progressEvents?.querySelectorAll("li[data-live='true']").forEach((row) => {
    if (exceptKey && row.dataset.eventKey === exceptKey) return;
    row.dataset.live = "false";
    row.dataset.done = "true";
    delete row.dataset.stagePercent;
    row.classList.remove("is-live");
    row.classList.add("is-done");
    const timeEl = row.querySelector("time");
    if (timeEl) timeEl.textContent = formatLiveEventDuration(row.dataset.startedAt);
    const marker = row.querySelector(".event-marker, .event-percent");
    if (marker) {
      marker.className = "event-marker";
      marker.innerHTML = "&#10003;";
    }
  });
}
function renderProgressEventRow(info, eventTime = null, row = null) {  // builds the event row HTML with local percent and stopwatch time
  const done = row?.dataset?.done === "true" || info.complete;
  const hasPercent = !done && Number.isFinite(Number(info.stagePercent));
  const markerHtml = info.started ? "" : done ? "&#10003;" : hasPercent ? `${Number(info.stagePercent).toFixed(0)}%` : `<span class="event-dot" aria-hidden="true"></span>`;
  const markerClass = hasPercent ? "event-percent" : "event-marker";
  const startMs = Number(row?.dataset?.startedAt) || Number(eventTime) || Date.parse(eventTime || "") || Date.now();
  const timeText = info.started ? "" : done ? formatLiveEventDuration(startMs) : `+${formatLiveEventDuration(startMs)}`;
  return `<span class="${markerClass}">${markerHtml}</span><span class="event-message">${escapeHtml(info.message)}</span><time>${timeText}</time>`;
}
function refreshProgressEventTimers() {  // updates live progress event stopwatch labels every second
  const liveRows = progressEvents?.querySelectorAll("li[data-live='true']") || [];
  liveRows.forEach((row) => {
    const timeEl = row.querySelector("time");
    if (!timeEl) return;
    timeEl.textContent = `+${formatLiveEventDuration(row.dataset.startedAt)}`;
  });
  if (progressEventsCount && jobStartTimestamp) {
    const hasOpenLiveRows = Boolean(progressEvents?.querySelector("li[data-live='true']"));
    progressEventsCount.textContent = hasOpenLiveRows ? `Running ${formatLiveEventDuration(jobStartTimestamp)}` : progressEventsCount.textContent;
  }
}
function addProgressEvent(message, percent = null, eventTime = null, stage = null) {  // adds or updates one clean progress event in the status panel
  if (!progressEvents) return;
  const info = normalizeProgressEvent(message, percent, stage);
  if (!info) return;
  const key = info.key;
  const existing = renderedProgressEvents.get(key);
  if (existing?.dataset?.done === "true" && info.live) return;
  if (info.live) freezeLiveProgressRows(key);
  if (existing) {
    if (Number.isFinite(Number(info.stagePercent))) existing.dataset.stagePercent = String(info.stagePercent);
    else delete existing.dataset.stagePercent;
    existing.dataset.live = info.live ? "true" : "false";
    existing.dataset.done = (info.complete || (!info.live && !info.started)) ? "true" : existing.dataset.done || "false";
    existing.classList.toggle("is-live", Boolean(info.live));
    existing.classList.toggle("is-done", existing.dataset.done === "true");
    existing.innerHTML = renderProgressEventRow(info, existing.dataset.startedAt || eventTime, existing);
    return;
  }
  if (seenProgressEvents.has(key)) return;
  seenProgressEvents.add(key);
  const li = document.createElement("li");
  li.dataset.eventKey = key;
  li.dataset.startedAt = String(Date.parse(eventTime || "") || Date.now());
  li.dataset.live = info.live ? "true" : "false";
  li.dataset.done = (info.complete || (!info.live && !info.started)) ? "true" : "false";
  if (Number.isFinite(Number(info.stagePercent))) li.dataset.stagePercent = String(info.stagePercent);
  li.classList.toggle("is-live", Boolean(info.live));
  li.classList.toggle("is-start", Boolean(info.started));
  li.classList.toggle("is-complete", Boolean(info.complete));
  li.classList.toggle("is-done", li.dataset.done === "true");
  li.innerHTML = renderProgressEventRow(info, eventTime, li);
  renderedProgressEvents.set(key, li);
  progressEvents.prepend(li);
  while (progressEvents.children.length > 8) {
    const removed = progressEvents.lastElementChild;
    if (removed?.dataset?.eventKey) renderedProgressEvents.delete(removed.dataset.eventKey);
    removed?.remove();
  }
  progressEventCounter += 1;
  if (progressEventsCount) progressEventsCount.textContent = jobStartTimestamp ? `Running ${formatLiveEventDuration(jobStartTimestamp)}` : `${progressEventCounter} updates`;
}
function syncProgressEvents(job) {  // renders progress events received from backend job state
  const events = Array.isArray(job?.progress_events) ? job.progress_events : [];
  if (events.length && !renderedProgressEvents.has("job-started")) {
    const firstTime = events[0]?.time || null;
    const firstMs = firstTime ? Date.parse(firstTime) : 0;
    if (firstMs && (!jobStartTimestamp || firstMs < jobStartTimestamp)) jobStartTimestamp = firstMs;
    const startText = firstTime ? new Date(firstTime).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "job start";
    addProgressEvent(`Started at ${startText}`, null, firstTime, 1);
  }
  events.slice(-12).forEach((event) => addProgressEvent(event.message, event.percent, event.time, event.stage));
  if (!events.length && job?.latest_log) addProgressEvent(job.latest_log, job.progress_percent, null, job.progress_stage);
  if (job?.status === "completed") {
    freezeLiveProgressRows();
    const completedAt = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    addProgressEvent(`Completed at ${completedAt} | Total ${progressEventElapsedLabel()}`, 100, new Date().toISOString(), 10);
    if (progressEventsCount) progressEventsCount.textContent = `Completed ${progressEventElapsedLabel()}`;
  }
  refreshProgressEventTimers();
}
function updateProgressTiming(percent) {  // refreshes the Progress Timing UI/state
  const pct = Math.max(0, Math.min(100, Number(percent) || 0));
  if (progressPct) progressPct.textContent = `${pct.toFixed(2)}%`;
  if (!jobStartTimestamp) {
    if (progressElapsed) progressElapsed.textContent = "Elapsed 00:00";
    if (progressEta) progressEta.textContent = "ETA --:--";
    return;
  }
  const elapsed = (Date.now() - jobStartTimestamp) / 1000;
  if (progressElapsed) progressElapsed.textContent = `Elapsed ${formatDuration(elapsed)}`;
  if (progressEta) {
    if (pct > 1 && pct < 100) {
      const total = elapsed / (pct / 100);
      progressEta.textContent = `ETA ${formatDuration(total - elapsed)}`;
    } else if (pct >= 100) {
      progressEta.textContent = "ETA 00:00";
    } else {
      progressEta.textContent = "ETA --:--";
    }
  }
}
function setStatus(message) {  // sets the Status value in the UI/state
  const text = String(message || "");
  statusText.textContent = text;
  localStorage.setItem(STORAGE_KEYS.lastStatus, text);
}
function setProgress(percent, label) {  // sets the Progress value in the UI/state
  const cleanPercent = Math.max(0, Math.min(100, Number(percent) || 0));

  if (progressBar) {
    progressBar.style.width = `${cleanPercent}%`;
    progressBar.setAttribute("aria-valuenow", String(cleanPercent));
    progressBar.textContent = `${cleanPercent.toFixed(0)}%`;
  }

  if (progressStep) {
    progressStep.textContent = "";
    progressStep.hidden = true;
  }

  updateProgressTiming(cleanPercent);
}
function setCurrentJob(jobId) {  // sets the Current Job value in the UI/state
  currentJobId = jobId || null;

  if (currentJobId) {
    localStorage.setItem(STORAGE_KEYS.lastJob, currentJobId);
    localStorage.setItem(STORAGE_KEYS.pendingJob, currentJobId);

    if (currentJobLabel) {
      currentJobLabel.textContent = `Current Job: ${currentJobId}`;
    }

    if (resumeJobId) {
      resumeJobId.value = currentJobId;
    }
  } else {
    if (currentJobLabel) {
      currentJobLabel.textContent = "No active job";
    }
  }
}
function setPendingJob(jobId) {  // sets the Pending Job value in the UI/state
  if (!jobId) return;

  localStorage.setItem(STORAGE_KEYS.pendingJob, jobId);
  localStorage.setItem(STORAGE_KEYS.lastJob, jobId);
  currentJobId = jobId;

  if (currentJobLabel) {
    currentJobLabel.textContent = `Current Job: ${jobId}`;
  }

  if (resumeJobId) {
    resumeJobId.value = jobId;
  }
}
function clearStoredJob() {  // clears the Stored Job UI/state
  localStorage.removeItem(STORAGE_KEYS.lastJob);
  localStorage.removeItem(STORAGE_KEYS.pendingJob);
  localStorage.removeItem(STORAGE_KEYS.lastStatus);

  currentJobId = null;

  jobStartTimestamp = 0;
  resetProgressEvents();
  setProgress(0, "Idle");
  setStatus("Waiting for input...");

  if (currentJobLabel) {
    currentJobLabel.textContent = "No active job";
  }

  if (resumeJobId) {
    resumeJobId.value = "";
  }

  resetResults();
}
function setButtonProcessing(active) {  // sets the Button Processing value in the UI/state
  generateBtn.disabled = Boolean(active);
  generateBtn.textContent = active ? "Processing..." : "Generate Shorts";
}
function resetResults() {  // clears previous shorts/thumbnails/metadata before a new job
  resultSection.classList.add("hidden");
  shortsList.innerHTML = "";
  thumbsList.innerHTML = "";
  metaList.innerHTML = "";

  if (filesList) {
    filesList.innerHTML = "";
  }

  if (resultSummary) {
    resultSummary.innerHTML = `
      <article>
        <strong>0</strong>
        <span>Shorts</span>
      </article>
      <article>
        <strong>0</strong>
        <span>Thumbnails</span>
      </article>
      <article>
        <strong>0</strong>
        <span>Metadata Files</span>
      </article>
      <article>
        <strong>ZIP</strong>
        <span>Export Package</span>
      </article>
    `;
  }

  setTextById("shortsCount", "0");
  setTextById("thumbsCount", "0");
  setTextById("metaCount", "0");
  zipDownload.href = "#";
  zipDownload.classList.add("disabled-link");

  activateResultTab("shortsPanel");
}
function setTextById(id, value) {  // sets the Text By Id value in the UI/state
  const el = document.getElementById(id);
  if (el) {
    el.textContent = String(value);
  }
}
function activateResultTab(panelId) {  // switches the Results UI between shorts, thumbnails, metadata, and files
  document.querySelectorAll(".result-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.resultTab === panelId);
  });

  document.querySelectorAll(".result-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === panelId);
    if (panel.id === panelId) revealFreshContent(panel);
  });
}
function setupResultTabs() {  // sets the up Result Tabs value in the UI/state
  resultTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      activateResultTab(tab.dataset.resultTab);
    });
  });
}
function updateResultSummary(shorts, thumbnails, metadata, downloadZip) {  // refreshes the Result Summary UI/state
  const shortsCount = shorts.length;
  const thumbsCount = thumbnails.length;
  const metaCountValue = metadata.length;
  setTextById("shortsCount", shortsCount);
  setTextById("thumbsCount", thumbsCount);
  setTextById("metaCount", metaCountValue);
  if (!resultSummary) return;

  resultSummary.innerHTML = `
    <article>
      <strong>${shortsCount}</strong>
      <span>Generated Shorts</span>
    </article>
    <article>
      <strong>${thumbsCount}</strong>
      <span>Thumbnails</span>
    </article>
    <article>
      <strong>${metaCountValue}</strong>
      <span>Metadata Files</span>
    </article>
    <article>
      <strong>${downloadZip ? "Ready" : "Missing"}</strong>
      <span>ZIP Export</span>
    </article>
  `;
}
function switchMode(nextMode) {  // switches input mode between upload, link, and local library selection
  mode = nextMode;

  if (mode === "upload") {
    uploadTab.classList.add("active");
    linkTab.classList.remove("active");
    uploadBox.classList.remove("hidden");
    linkBox.classList.add("hidden");
  } else {
    linkTab.classList.add("active");
    uploadTab.classList.remove("active");
    linkBox.classList.remove("hidden");
    uploadBox.classList.add("hidden");
  }

  updateInputUnlock();
  updateFlowSummary();
}
function getPredictedUploadJobId(file) {  // returns the current Predicted Upload Job Id value
  if (!file || !file.name) return "";

  const fileName = file.name;
  const lastDot = fileName.lastIndexOf(".");
  const stem = lastDot > 0 ? fileName.slice(0, lastDot) : fileName;

  return stem.replaceAll(" ", "_");
}
function buildFormData() {  // collects frontend controls into the FormData sent to FastAPI
  const formData = new FormData();

  formData.append("platform", "youtube");
  formData.append("aspect_ratio", getValue("aspectRatio"));
  formData.append("output_resolution", getValue("outputResolution") || "1080p");
  formData.append("segment_mode", getValue("segmentMode"));
  formData.append("clip_duration_seconds", getValue("clipDuration"));
  formData.append("manual_ranges", getValue("manualRanges"));

  formData.append("captions", getValue("captions"));
  formData.append("filter_preset", getValue("filterPreset"));
  formData.append("reframe", getValue("reframe"));

  formData.append("font_preset", getValue("fontPreset"));
  formData.append("caption_position", getValue("captionPosition"));
  formData.append("caption_size", getValue("captionSize"));
  formData.append("font_family", getValue("fontFamily"));
  formData.append("caption_case", getValue("captionCase") || "preset");

  formData.append("editing_style", getEffectiveEditingStyle());

  formData.append("music_enabled", getValue("musicEnabled"));
  formData.append("music_category", getValue("musicCategory"));
  formData.append("music_volume", getValue("musicVolume"));
  const selectedTrackCategory = selectedMusicCategory || "";
  const currentMusicCategory = getValue("musicCategory") || "";
  const currentTrack = selectedTrackCategory === currentMusicCategory ? selectedMusicTrack : "";
  formData.append("music_track", currentTrack || "");

  return formData;
}
function escapeHtml(value) {  // escapes text before inserting it into HTML safely
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
function makeApiUrl(pathOrUrl) {  // builds an absolute backend API URL from a relative path
  if (!pathOrUrl) return "#";

  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }

  return `${API_BASE}${pathOrUrl}`;
}
function guessMimeType(fileName = "") {  // chooses a download MIME type from a file extension
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".mp4")) return "video/mp4";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".txt")) return "text/plain";
  if (lower.endsWith(".zip")) return "application/zip";
  return "application/octet-stream";
}
async function downloadAsset(pathOrUrl, fileName = "clipforge-download") {  // downloads one generated asset from the browser
  try {
    const url = makeApiUrl(pathOrUrl);
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`Download failed with status ${response.status}`);

    const blob = await response.blob();
    const safeName = fileName || "clipforge-download";

    if (window.showSaveFilePicker) {
      const extension = safeName.includes(".") ? `.${safeName.split(".").pop()}` : ".bin";
      const handle = await window.showSaveFilePicker({
        suggestedName: safeName,
        types: [{
          description: "ClipForge output file",
          accept: { [guessMimeType(safeName)]: [extension] },
        }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }

    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = safeName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1500);
  } catch (error) {
    alert("Download failed: " + error.message);
  }
}

window.downloadAsset = downloadAsset;
async function fetchJson(url, options = {}) {  // fetches JSON from the backend and throws useful errors on failure
  const mergedOptions = { ...options };
  mergedOptions.headers = { ...authHeaders(), ...(options.headers || {}) };
  const response = await fetch(url, mergedOptions);
  let data = null;

  try {
    data = await response.json();
  } catch (error) {
    data = { error: "Invalid JSON response from backend." };
  }

  if (!response.ok || data.error) {
    throw new Error(
      data.error || data.details || `Request failed with status ${response.status}`
    );
  }

  return data;
}
async function fetchTextFromUrl(pathOrUrl) {  // loads text metadata/report content from a backend URL
  const url = makeApiUrl(pathOrUrl);

  const response = await fetch(url, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Could not load metadata file: ${response.status}`);
  }

  return await response.text();
}
async function copyMetadataText(button) {  // copies a full metadata block to the clipboard
  try {
    const card = button.closest(".meta-card");
    const preview = card.querySelector(".metadata-preview");

    if (!preview) {
      throw new Error("Metadata text not found.");
    }

    await navigator.clipboard.writeText(preview.innerText);

    const oldText = button.textContent;
    button.textContent = "Copied";

    setTimeout(() => {
      button.textContent = oldText;
    }, 1500);
  } catch (error) {
    alert("Copy failed: " + error.message);
  }
}
async function copyMetaFieldText(button, fieldName) {  // copies one metadata field such as title, hook, or hashtags
  try {
    const card = button.closest(".meta-card");
    const field = card.querySelector(`[data-meta-field="${fieldName}"]`);

    if (!field) {
      throw new Error("Field text not found.");
    }

    await navigator.clipboard.writeText(field.innerText.trim());

    const oldText = button.textContent;
    button.textContent = "Copied";

    setTimeout(() => {
      button.textContent = oldText;
    }, 1500);
  } catch (error) {
    alert("Copy failed: " + error.message);
  }
}
async function copyAllStructuredMetadata(button) {  // copies all structured metadata fields together
  try {
    const card = button.closest(".meta-card");
    const box = card.querySelector(".structured-meta");

    if (!box) {
      throw new Error("Structured metadata not found.");
    }

    await navigator.clipboard.writeText(box.innerText.trim());

    const oldText = button.textContent;
    button.textContent = "Copied All";

    setTimeout(() => {
      button.textContent = oldText;
    }, 1500);
  } catch (error) {
    alert("Copy failed: " + error.message);
  }
}
function escapeRegex(value) {  // escapes text so it can be used inside a regular expression
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function normalizeMetadataText(value) {  // cleans metadata text before parsing display fields
  return String(value || "")
    .replaceAll("???", "-")
    .replaceAll("???", "'")
    .replaceAll("???", '"')
    .replaceAll("???", '"')
    .replaceAll("????", "")
    .replaceAll("????", "")
    .replaceAll("???", "")
    .trim();
}
function extractMetadataBlock(content, labels, stopLabels) {  // extracts a named metadata section from a text file
  const text = String(content || "").replace(/\r\n/g, "\n");
  const labelPattern = labels.map(escapeRegex).join("|");
  const stopPattern = stopLabels.map(escapeRegex).join("|");

  const regex = new RegExp(
    `(?:^|\\n)\\s*(?:${labelPattern})\\s*[:\\-]\\s*([\\s\\S]*?)(?=\\n\\s*(?:${stopPattern})\\s*[:\\-]|$)`,
    "i"
  );

  const match = text.match(regex);
  return match ? normalizeMetadataText(match[1]) : "";
}
function firstNonEmptyLine(text) {  // returns the first useful line from a block of text
  return String(text || "").split("\n").map((line) => line.trim()).find(Boolean) || "";
}
function extractMetadataFields(content) {  // parses title, hook, description, hashtags, and CTA from metadata text
  const text = String(content || "").trim();

  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object") {
      return {
        hook: normalizeMetadataText(parsed.hook || parsed.Hook || ""),
        title: normalizeMetadataText(parsed.title || parsed.Title || ""),
        description: normalizeMetadataText(parsed.description || parsed.Description || ""),
        hashtags: normalizeMetadataText(parsed.hashtags || parsed.Hashtags || ""),
        hashtagsComma: normalizeMetadataText(parsed.hashtags_comma || parsed.hashtagsComma || ""),
        cta: normalizeMetadataText(parsed.cta || parsed.CTA || parsed.call_to_action || ""),
      };
    }
  } catch (error) {
    // Metadata is usually plain text, so JSON failure is okay.
  }

  const stopLabels = [
    "TITLE",
    "Title",
    "Video Title",
    "HOOK OPTIONS",
    "Hook Options",
    "Hook",
    "Viral Hook",
    "DESCRIPTION",
    "Description",
    "Video Description",
    "HASHTAGS",
    "Hashtags",
    "Hash Tags",
    "HASHTAGS COMMA",
    "META",
    "CLIP RANGE",
    "KEYWORDS HIT",
    "CTA",
    "Call To Action",
    "Call-to-Action",
  ];

  const titleBlock = extractMetadataBlock(text, ["TITLE", "Title", "Video Title"], stopLabels);
  const hookBlock = extractMetadataBlock(text, ["HOOK OPTIONS", "Hook Options", "Hook", "Viral Hook"], stopLabels);
  const descriptionBlock = extractMetadataBlock(text, ["DESCRIPTION", "Description", "Video Description"], stopLabels);
  const hashtagsBlock = extractMetadataBlock(text, ["HASHTAGS", "Hashtags", "Hash Tags"], ["HASHTAGS COMMA", "META", "CLIP RANGE", "KEYWORDS HIT", "CTA", "Call To Action", "Call-to-Action"]);
  const hashtagsCommaBlock = extractMetadataBlock(text, ["HASHTAGS COMMA"], ["META", "CLIP RANGE", "KEYWORDS HIT", "CTA", "Call To Action", "Call-to-Action"]);

  return {
    hook: hookBlock || firstNonEmptyLine(descriptionBlock),
    title: titleBlock,
    description: descriptionBlock,
    hashtags: hashtagsBlock,
    hashtagsComma: hashtagsCommaBlock,
    cta: extractMetadataBlock(text, ["CTA", "Call To Action", "Call-to-Action"], stopLabels),
  };
}
function formatMetaValue(value, fieldName) {  // formats parsed metadata values for display/copy controls
  const cleanValue = normalizeMetadataText(value);
  if (!cleanValue) return "Not found in this metadata file.";
  if (fieldName === "hook") return firstNonEmptyLine(cleanValue.replace(/^[-?]\s*/gm, ""));
  return cleanValue;
}
function renderMetaField(label, value, fieldName) {  // renders the render Meta Field section from current app state
  const cleanValue = formatMetaValue(value, fieldName);
  const isMissing = cleanValue === "Not found in this metadata file.";

  return `
    <section class="meta-field meta-field-${fieldName}">
      <div class="meta-field-head">
        <strong>${escapeHtml(label)}</strong>
        <button type="button" onclick="copyMetaFieldText(this, '${fieldName}')">Copy</button>
      </div>
      <p data-meta-field="${fieldName}" class="${isMissing ? "missing" : ""}">${escapeHtml(cleanValue)}</p>
    </section>
  `;
}

setupCreatorFlow();

uploadTab.addEventListener("click", () => switchMode("upload"));
linkTab.addEventListener("click", () => switchMode("link"));
refreshProjectInputBtn?.addEventListener("click", loadProjectInputLibrary);

clearJobBtn.addEventListener("click", () => {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }

  clearStoredJob();
  setButtonProcessing(false);
});

resumeJobBtn.addEventListener("click", async () => {
  const jobId = resumeJobId.value.trim();

  if (!jobId) {
    setStatus("Please enter a Job ID to resume.");
    return;
  }

  resetResults();
  jobStartTimestamp = Date.now();
  resetProgressEvents();
  setCurrentJob(jobId);
  setButtonProcessing(true);
  setProgress(15, "Resuming job");
  setStatus(`Resuming job...
Job ID: ${jobId}
Asking backend to continue this job...`);

  try {
    const response = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}/resume`, {
      method: "POST",
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || data.details || `Resume failed: ${response.status}`);
    }
    setStatus(`${data.message || "Job resumed."}
Job ID: ${jobId}`);
  } catch (error) {
    setStatus(`Resume request failed. Polling existing status instead.
Job ID: ${jobId}
Reason: ${error.message}`);
  }

  startPolling(jobId);
});

generateBtn.addEventListener("click", async (event) => {
  event.preventDefault();

  if (isSubmitting) return;

  resetResults();
  jobStartTimestamp = Date.now();
  resetProgressEvents();
  setProgress(8, "Starting");
  setStatus("Starting process...");
  renderTimeline(0);

  try {
    isSubmitting = true;

    if (getValue("segmentMode") === "manual" && !manualRangesState.length) {
      throw new Error("Manual Ranges mode needs at least one clip range. Add start and end time first.");
    }

    const formData = buildFormData();
    let endpoint = "";

    if (mode === "upload") {
      const fileInput = document.getElementById("videoFile");

      if (selectedProjectInputPath) {
        const predictedJobId = (selectedProjectInputName || selectedProjectInputPath).replace(/\.[^.]+$/, "").replaceAll(" ", "_");
        setPendingJob(predictedJobId);
        formData.append("local_input_path", selectedProjectInputPath);
        endpoint = `${API_BASE}/process-local-input`;
        setStatus(`Using project input video:\n${selectedProjectInputPath}`);
      } else {
        if (!fileInput.files.length) {
          setProgress(0, "Idle");
          setStatus("Please select a video file or choose one from Project input folder.");
          isSubmitting = false;
          return;
        }

        const selectedFiles = Array.from(fileInput.files);

        if (selectedFiles.length === 1) {
          const selectedFile = selectedFiles[0];
          const predictedJobId = getPredictedUploadJobId(selectedFile);

          setPendingJob(predictedJobId);
          formData.append("video", selectedFile);
          endpoint = `${API_BASE}/process-upload`;
        } else {
          selectedFiles.forEach((file) => formData.append("videos", file));
          endpoint = `${API_BASE}/process-batch-upload`;
          clearStoredJob();
          setStatus(`Uploading ${selectedFiles.length} videos for batch processing...`);
        }
      }
    } else {
      const url = getValue("videoUrl").trim();

      if (!url) {
        setProgress(0, "Idle");
        setStatus("Please paste a video link.");
        isSubmitting = false;
        return;
      }

      formData.append("video_url", url);
      endpoint = `${API_BASE}/process-link`;
    }
    setButtonProcessing(true);
    setProgress(15, "Uploading / submitting");

    const data = await fetchJson(endpoint, {
      method: "POST",
      body: formData,
    });

    if (!data.job_id) {
      throw new Error("Backend did not return job_id.");
    }

    setCurrentJob(data.job_id);
    setProgress(25, "Job started");

    setStatus(
      `Job started successfully.\nJob ID: ${data.job_id}\nChecking progress...`
    );

    startPolling(data.job_id);
  } catch (error) {
    setProgress(0, "Error");
    setStatus("Error:\n" + error.message);
    setButtonProcessing(false);
  } finally {
    isSubmitting = false;
  }
});
function startPolling(jobId) {  // starts repeated backend status checks during processing
  if (!jobId) return;
  if (!jobStartTimestamp) jobStartTimestamp = Date.now();

  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
  async function checkStatus() {  // checks one backend job status during polling
    try {
      const data = await fetchJson(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`);
      syncProgressEvents(data);

      if (data.status === "queued") {
        setProgressForJob(data, 1, "Queued");
        setTimelineForStatus(data);
        const batchLine = data.type === "batch" ? `\nBatch: ${data.completed || 0}/${data.total || 0} videos` : "";
        setStatus(
          `Your ${data.type === "batch" ? "batch" : "video"} is queued.\nJob ID: ${jobId}${batchLine}\nWaiting to start processing...`
        );
        setButtonProcessing(true);
      } else if (data.status === "processing") {
        setProgressForJob(data, 2, "Processing");
        setTimelineForStatus(data);
        const batchLine = data.type === "batch" ? `\nBatch: ${data.completed || 0}/${data.total || 0} videos` : "";
        const stageLabel = getBackendStageLabel(data, "Processing");
        setStatus(
          `Processing your ${data.type === "batch" ? "batch" : "video"}...\nJob ID: ${jobId}${batchLine}\nCurrent stage: ${stageLabel}\n\nDo not start another job until this finishes.`
        );
        setButtonProcessing(true);
      } else if (data.status === "completed") {
        clearInterval(pollingTimer);
        pollingTimer = null;

        setCurrentJob(jobId);
        setProgress(90, "Loading results");
        setTimelineForStatus({ ...data, progress_stage: TIMELINE_STAGES.length });
        setStatus(data.type === "batch" ? `Batch completed: ${data.completed || data.total || 0}/${data.total || 0} videos. Loading your results...` : "Processing completed successfully. Loading your results...");

        await loadResults(jobId);

        setProgress(100, "Completed");
        addProgressEvent("Job Complete", 100);
        setButtonProcessing(false);
      } else if (data.status === "failed") {
        clearInterval(pollingTimer);
        pollingTimer = null;

        const failedReason = data.error || "Unknown error";
        const interruptedAfterBackendRestart = /Backend was stopped before this job finished/i.test(failedReason);

        localStorage.removeItem(STORAGE_KEYS.pendingJob);

        if (interruptedAfterBackendRestart) {
          clearStoredJob();
          setStatus("Waiting for input...");
          return;
        }

        setProgress(0, "Failed");
        setTimelineForStatus(data);
        setStatus("Processing failed:\n" + failedReason);
        setButtonProcessing(false);
      } else {
        setProgress(45, "Checking");
        setStatus(`Current status: ${data.status || "unknown"}\nJob ID: ${jobId}`);
        setButtonProcessing(true);
      }
    } catch (error) {
      setProgress(20, "Retrying");
      setStatus(
        `Status check failed, retrying...\nJob ID: ${jobId}\nReason: ${error.message}`
      );
      setButtonProcessing(true);
    }
  }

  checkStatus();
  pollingTimer = setInterval(checkStatus, 3000);
}
setInterval(refreshProgressEventTimers, 1000);

async function loadResults(jobId) {  // loads load Results data into the browser UI
  try {
    const data = await fetchJson(`${API_BASE}/jobs/${encodeURIComponent(jobId)}/result`);

    const shorts = data.shorts || [];
    const thumbnails = data.thumbnails || [];
    const metadata = data.metadata || [];
    const downloadZip = data.download_zip || "";

    resultSection.classList.remove("hidden");

    updateResultSummary(shorts, thumbnails, metadata, downloadZip);

    renderShorts(shorts);
    renderThumbnails(thumbnails);
    await renderMetadata(metadata);
    if (downloadZip) {
      zipDownload.href = makeApiUrl(downloadZip);
      zipDownload.classList.remove("disabled-link");
    } else {
      zipDownload.href = "#";
      zipDownload.classList.add("disabled-link");
    }

    localStorage.removeItem(STORAGE_KEYS.pendingJob);
    localStorage.setItem(STORAGE_KEYS.lastJob, jobId);

    activateResultTab("shortsPanel");
    setStatus("Completed successfully. Results loaded.");

    setTimeout(() => {
      resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 200);
  } catch (error) {
    setStatus(
      `Completed, but result loading failed.\nJob ID: ${jobId}\nReason: ${error.message}\n\nOpen manually:\n${API_BASE}/jobs/${jobId}/result`
    );
    setButtonProcessing(false);
  }
}
function renderShorts(shorts) {  // renders the render Shorts section from current app state
  shortsList.innerHTML = `<div class="section-title"><h4>Generated Shorts</h4><span>${shorts.length}</span></div>`;

  if (!shorts.length) {
    shortsList.innerHTML += `<p class="empty-state">No shorts found.</p>`;
    return;
  }

  const cards = shorts
    .map((item, index) => {
      const url = makeApiUrl(item.url);
      const name = escapeHtml(item.name || `Short ${index + 1}`);

      return `
        <article class="result-card video-card">
          <div class="card-header">
            <strong>Short ${index + 1}</strong>
            <span>${name}</span>
          </div>
          <video controls preload="metadata" src="${url}"></video>
          <div class="card-actions">
            <a href="${url}" target="_blank" rel="noopener">Open</a>
            <button type="button" onclick="downloadAsset('${url}', '${name}')">Download</button>
          </div>
        </article>
      `;
    })
    .join("");

  shortsList.innerHTML += `<div class="result-grid">${cards}</div>`;
}
function renderThumbnails(thumbnails) {  // renders the render Thumbnails section from current app state
  thumbsList.innerHTML = `<div class="section-title"><h4>Thumbnails</h4><span>${thumbnails.length}</span></div>`;

  if (!thumbnails.length) {
    thumbsList.innerHTML += `<p class="empty-state">No thumbnails found.</p>`;
    return;
  }

  const cards = thumbnails
    .map((item, index) => {
      const url = makeApiUrl(item.url);
      const name = escapeHtml(item.name || `Thumbnail ${index + 1}`);

      return `
        <article class="result-card thumb-card">
          <div class="card-header">
            <strong>Thumbnail ${index + 1}</strong>
            <span>${name}</span>
          </div>
          <img src="${url}" alt="Thumbnail ${index + 1}" loading="lazy" />
          <div class="card-actions">
            <a href="${url}" target="_blank" rel="noopener">Open</a>
            <button type="button" onclick="downloadAsset('${url}', '${name}')">Download</button>
          </div>
        </article>
      `;
    })
    .join("");

  thumbsList.innerHTML += `<div class="result-grid">${cards}</div>`;
}
async function renderMetadata(metadata) {  // renders the render Metadata section from current app state
  metaList.innerHTML = `<div class="section-title"><h4>Structured Metadata</h4><span>${metadata.length}</span></div>`;

  if (!metadata.length) {
    metaList.innerHTML += `<p class="empty-state">No metadata found.</p>`;
    return;
  }

  let cards = "";

  for (let index = 0; index < metadata.length; index++) {
    const item = metadata[index];
    const url = makeApiUrl(item.url);
    const name = escapeHtml(item.name || `Metadata ${index + 1}`);

    let content = "";

    try {
      content = await fetchTextFromUrl(item.url);
    } catch (error) {
      content =
        "Metadata preview could not be loaded inside the dashboard.\n\n" +
        "You can still open or download the metadata file using the buttons below.\n\n" +
        "Reason: " +
        error.message;
    }

    const fields = extractMetadataFields(content);

    const trimmedContent =
      content.length > 2500
        ? content.slice(0, 2500) + "\n\n... Preview shortened. Open file for full metadata."
        : content;

    cards += `
      <article class="result-card meta-card">
        <div class="card-header">
          <strong>Metadata ${index + 1}</strong>
          <span>${name}</span>
        </div>

        <div class="structured-meta">
          ${renderMetaField("Title", fields.title, "title")}
          ${renderMetaField("Hook", fields.hook, "hook")}
          ${renderMetaField("Description", fields.description, "description")}
          ${renderMetaField("Hashtags", fields.hashtags, "hashtags")}
          ${renderMetaField("Comma Tags", fields.hashtagsComma, "hashtagsComma")}
          ${fields.cta ? renderMetaField("CTA", fields.cta, "cta") : ""}
        </div>

        <div class="card-actions metadata-actions">
          <button type="button" onclick="copyAllStructuredMetadata(this)">Copy All</button>
          <button type="button" onclick="copyMetadataText(this)">Copy Raw Text</button>
          <a href="${url}" target="_blank" rel="noopener">Open Metadata</a>
          <button type="button" onclick="downloadAsset('${url}', '${name}')">Download</button>
        </div>

        <details class="raw-metadata-box">
          <summary>View raw metadata text</summary>
          <pre class="metadata-preview">${escapeHtml(trimmedContent)}</pre>
        </details>
      </article>
    `;
  }

  metaList.innerHTML += `<div class="result-grid metadata-grid">${cards}</div>`;
}
function renderFiles(jobId, shorts, thumbnails, metadata, downloadZip) {  // renders the render Files section from current app state
  if (!filesList) return;

  const files = [];

  if (downloadZip) {
    files.push({
      type: "ZIP",
      name: `${jobId || "clipforge"}_outputs.zip`,
      url: downloadZip,
      label: "Complete export package",
    });
  }

  shorts.forEach((item, index) => {
    files.push({
      type: "Video",
      name: item.name || `Short ${index + 1}`,
      url: item.url,
      label: "Generated short video",
    });
  });

  thumbnails.forEach((item, index) => {
    files.push({
      type: "Image",
      name: item.name || `Thumbnail ${index + 1}`,
      url: item.url,
      label: "Generated thumbnail",
    });
  });

  metadata.forEach((item, index) => {
    files.push({
      type: "Text",
      name: item.name || `Metadata ${index + 1}`,
      url: item.url,
      label: "Posting metadata",
    });
  });

  filesList.innerHTML = `<div class="section-title"><h4>Output Files</h4><span>${files.length}</span></div>`;

  if (!files.length) {
    filesList.innerHTML += `<p class="empty-state">No output files found.</p>`;
    return;
  }

  const cards = files
    .map((file) => {
      const url = makeApiUrl(file.url);
      const name = escapeHtml(file.name);
      const type = escapeHtml(file.type);
      const label = escapeHtml(file.label);

      return `
        <article class="result-card file-card">
          <div class="file-row">
            <div>
              <span class="file-type-badge">${type}</span>
              <h4>${name}</h4>
              <p>${label}</p>
            </div>

            <div class="card-actions">
              <a href="${url}" target="_blank" rel="noopener">Open</a>
              <button type="button" onclick="downloadAsset('${url}', '${name}')">Download</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  filesList.innerHTML += `<div class="file-list">${cards}</div>`;
}
function restorePreviousJobOnLoad() {  // resumes only an active in-progress job after browser refresh; completed old jobs require manual Job ID resume
  const pendingJob = localStorage.getItem(STORAGE_KEYS.pendingJob);

  resetProgressEvents();
  resetResults();

  if (!pendingJob) {
    currentJobId = null;
    jobStartTimestamp = 0;
    localStorage.removeItem(STORAGE_KEYS.lastStatus);
    setProgress(0, "Idle");
    setStatus("Waiting for input...");
    setButtonProcessing(false);

    if (currentJobLabel) {
      currentJobLabel.textContent = "No active job";
    }

    if (resumeJobId) {
      resumeJobId.value = "";
    }

    return;
  }

  currentJobId = pendingJob;

  if (currentJobLabel) {
    currentJobLabel.textContent = `Current Job: ${pendingJob}`;
  }

  if (resumeJobId) {
    resumeJobId.value = pendingJob;
  }

  setButtonProcessing(true);
  setProgress(20, "Resuming");
  setStatus(`Resuming active job after refresh...\nJob ID: ${pendingJob}\nChecking backend status...`);
  startPolling(pendingJob);
}
function setupThemeMode() {  // sets the up Theme Mode value in the UI/state
  if (!themeToggle) return;

  const label = themeToggle.querySelector(".theme-toggle-text");
  const sunIcon = themeToggle.querySelector(".theme-icon-sun");
  const moonIcon = themeToggle.querySelector(".theme-icon-moon");
  const storedTheme = localStorage.getItem(STORAGE_KEYS.theme);
  const prefersLight = window.matchMedia?.("(prefers-color-scheme: light)")?.matches;
  let activeTheme = storedTheme || (prefersLight ? "light" : "dark");
  function applyTheme(theme) {  // applies the saved dark/light theme to the page
    activeTheme = theme === "light" ? "light" : "dark";
    document.body.dataset.theme = activeTheme;
    localStorage.setItem(STORAGE_KEYS.theme, activeTheme);

    const isLight = activeTheme === "light";
    themeToggle.dataset.currentTheme = activeTheme;
    themeToggle.setAttribute("aria-label", isLight ? "Light mode active" : "Dark mode active");
    themeToggle.setAttribute("aria-pressed", String(isLight));
    themeToggle.title = isLight ? "Light mode" : "Dark mode";
    themeToggle.classList.toggle("is-light", isLight);
    themeToggle.classList.toggle("is-dark", !isLight);
    if (sunIcon) sunIcon.hidden = !isLight;
    if (moonIcon) moonIcon.hidden = isLight;
    if (label) label.textContent = isLight ? "Light mode" : "Dark mode";
  }

  themeToggle.addEventListener("click", () => {
    applyTheme(activeTheme === "light" ? "dark" : "light");
  });

  applyTheme(activeTheme);
}
function setupCursorGlow() {  // sets the up Cursor Glow value in the UI/state
  if (!cursorGlow || !cursorDot) return;
  const coarsePointer = window.matchMedia?.("(pointer: coarse)")?.matches;
  if (coarsePointer && window.innerWidth < 900) return;

  document.body.classList.add("cursor-glow-ready");
  function moveGlow(x, y) {  // moves the decorative cursor glow with pointer position
    document.documentElement.style.setProperty("--cursor-x", `${x}px`);
    document.documentElement.style.setProperty("--cursor-y", `${y}px`);
    document.documentElement.style.setProperty("--cursor-dot-x", `${x}px`);
    document.documentElement.style.setProperty("--cursor-dot-y", `${y}px`);
  }

  moveGlow(window.innerWidth / 2, window.innerHeight / 2);

  window.addEventListener("pointermove", (event) => {
    moveGlow(event.clientX, event.clientY);
  }, { passive: true });

  window.addEventListener("mousemove", (event) => {
    moveGlow(event.clientX, event.clientY);
  }, { passive: true });
}
function setupPageAnimations() {  // sets the up Page Animations value in the UI/state
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  const animatedSections = Array.from(document.querySelectorAll(
    "main > section, .hero-section, .clipforge-proof-section, .tools-section, .how-section, .features-section, .why-section, .pricing-section, .faq-section, .creator-section, .results-wrapper, .testimonials-section"
  ));

  const headingSelector = ":scope h1, :scope h2, :scope .section-title h2, :scope .faq-heading-wrap h2, :scope .creator-section-heading h2, :scope .results-header h3";
  const contentSelector = [
    ".hero-actions", ".hero-copy", ".hero-visual-wrap", ".proof-card", ".tool-card", ".how-card", ".feature-card",
    ".comparison-card", ".comparison-table", ".price-card", ".credit-card", ".faq-item", ".studio-shell",
    ".status-card", ".results", ".testimonial-marquee"
  ].join(", ");

  document.body.classList.add("motion-ready");

  animatedSections.forEach((section) => {
    section.classList.add("animate-section");
    const heading = section.querySelector(headingSelector);
    if (heading) {
      heading.classList.add("animate-heading");
      heading.dataset.animate = "heading";
      heading.style.setProperty("--delay", "0ms");
    }

    const items = Array.from(section.querySelectorAll(contentSelector)).filter((item) => {
      if (heading && item === heading) return false;
      return !item.closest(".testimonial-track") || item.classList.contains("testimonial-card");
    });

    items.forEach((item, index) => {
      item.classList.add("animate-fade-up");
      item.dataset.animate = "fade-up";
      item.style.setProperty("--delay", `${120 + Math.min(index, 10) * 90}ms`);
    });
  });

  document.querySelectorAll(".tool-card, .feature-card, .price-card, .credit-card, .faq-item, .result-card, .summary-card, .caption-preset-card, .creator-step, .testimonial-card").forEach((item) => {
    item.classList.add("card-hover");
  });

  document.querySelectorAll("button, .btn, .plan-btn, .nav-cta, .hero-quick-card .quick-action, .card-actions a, .footer-back").forEach((item) => {
    item.classList.add("button-glow");
  });

  const animated = Array.from(document.querySelectorAll("[data-animate]"));
  if (reduceMotion) {
    animated.forEach((item) => item.classList.add("is-visible"));
    document.body.classList.add("reduced-motion");
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.14, rootMargin: "0px 0px -8% 0px" });

  animated.forEach((item) => observer.observe(item));
}
function revealFreshContent(scope = document) {  // reveals newly loaded sections with lightweight animation
  if (document.body.classList.contains("reduced-motion")) return;
  scope.querySelectorAll?.(".result-card, .summary-card, .file-card, .caption-preset-card").forEach((item, index) => {
    item.classList.add("card-hover", "animate-fade-up", "is-visible");
    item.style.setProperty("--delay", `${Math.min(index, 8) * 70}ms`);
  });
}
function setupBillingToggle() {  // sets the up Billing Toggle value in the UI/state
  const toggle = document.getElementById("billingToggle");
  const monthlyLabel = document.getElementById("monthlyLabel");
  const yearlyLabel = document.getElementById("yearlyLabel");

  if (!toggle) return;
  function updateBillingUI() {  // refreshes the Billing UI/state
    const isYearly = toggle.checked;

    document.querySelectorAll("[data-plan-card]").forEach((card) => {
      const isMonthlyOnly = card.dataset.monthlyOnly === "true";

      if (isMonthlyOnly) {
        card.classList.remove("yearly-active");
        return;
      }

      const price = card.querySelector(".dynamic-price");
      const credits = card.querySelector(".dynamic-credits");
      const note = card.querySelector(".billing-note");

      card.classList.toggle("yearly-active", isYearly);

      if (price) {
        const monthlyValue = price.dataset.monthlyPrice || "";
        const yearlyValue = price.dataset.yearlyPrice || monthlyValue;
        const period = isYearly
          ? price.dataset.yearlyPeriod || "/month"
          : price.dataset.monthlyPeriod || "/month";

        price.classList.toggle("price-yearly", isYearly);
        price.innerHTML = isYearly
          ? `<span class="old-price">${monthlyValue}</span><span class="new-price">${yearlyValue}</span><span class="price-period">${period}</span>`
          : `${monthlyValue}<span class="price-period">${period}</span>`;
      }

      if (credits) {
        credits.textContent = isYearly
          ? credits.dataset.yearlyCredits
          : credits.dataset.monthlyCredits;
      }

      if (note) {
        note.textContent = isYearly
          ? note.dataset.yearlyNote
          : note.dataset.monthlyNote;
      }
    });

    if (monthlyLabel) {
      monthlyLabel.classList.toggle("active", !isYearly);
    }

    if (yearlyLabel) {
      yearlyLabel.classList.toggle("active", isYearly);
    }
  }
  monthlyLabel?.addEventListener("click", () => {
    toggle.checked = false;
    updateBillingUI();
  });

  yearlyLabel?.addEventListener("click", () => {
    toggle.checked = true;
    updateBillingUI();
  });

  toggle.addEventListener("change", updateBillingUI);
  updateBillingUI();
}


const benchmarkComparisonData = {
  opusclip: {
    logo: "OC",
    name: "OpusClip",
    description: "AI clipping platform focused on turning long videos into short social clips.",
    available: ["AI Clipping", "AI Highlight Detection", "Captions", "Auto Reframe", "Transcript", "Export", "Publishing", "Team Collaboration", "Brand Templates"],
    limited: ["Metadata", "Thumbnail", "Analytics", "API"],
    missing: ["Roman Urdu Workflow", "Raw Footage Mode", "Fixed Duration Mode", "Transcript Cache", "ZIP Package"],
    wins: ["Manual + AI Clipping", "Raw Footage Mode", "Roman Captions", "Metadata Included", "ZIP Export"]
  },
  submagic: {
    logo: "SM",
    name: "Submagic",
    description: "Caption-first short-form editor with AI editing and social video tools.",
    available: ["AI Captions", "AI Video Editing", "Caption Styling", "Magic Clips", "AI B-roll", "Templates", "Export"],
    limited: ["Auto Reframe", "Metadata", "Thumbnail", "Publishing", "API"],
    missing: ["Roman Urdu Workflow", "Raw Footage", "Transcript Cache", "ZIP Package"],
    wins: ["Raw Footage Mode", "Metadata Generator", "Transcript Cache", "ZIP Export", "Creator Studio"]
  },
  munch: {
    logo: "MU",
    name: "Munch",
    description: "Repurposing platform for finding clips and adapting content for social channels.",
    available: ["AI Clipping", "Repurposing", "Auto Reframe", "Metadata Assistance", "Publishing", "Content Optimization"],
    limited: ["Analytics", "Brand Management", "Scheduling"],
    missing: ["Raw Footage", "Manual Clip Selection", "Roman Workflow", "Transcript Cache", "ZIP Package"],
    wins: ["Manual Clipping", "Raw Footage Mode", "Roman Workflow", "ZIP Export", "Local Project Support"]
  },
  wayin: {
    logo: "WY",
    name: "Wayin",
    description: "Short-video workflow tool with clipping, captions, publishing, and integrations.",
    available: ["AI Clipping", "Captions", "Publishing", "Scheduling", "Google Drive", "API"],
    limited: ["Metadata", "Thumbnail", "Analytics", "Brand Tools"],
    missing: ["Raw Footage", "Roman Workflow", "Transcript Cache", "ZIP Package"],
    wins: ["Creator Studio", "Raw Footage Mode", "Roman Captions", "Transcript Cache", "ZIP Export"]
  },
  autoshorts: {
    logo: "AS",
    name: "AutoShorts",
    description: "Automation-focused tool for producing repeatable faceless short-video content.",
    available: ["Faceless Automation", "AI Videos", "Scheduling", "Publishing", "Captions"],
    limited: ["Templates", "Workflow Customization"],
    missing: ["Manual Clipping", "Semantic Clipping", "Raw Footage", "Metadata", "Thumbnail", "Transcript Cache", "ZIP Package"],
    wins: ["Manual Clip Control", "Semantic Clip Modes", "Video-Based Workflow", "Metadata + Thumbnails", "ZIP Package Export"]
  }
};

const clipforgeBenchmarkFeatures = {
  summary: [
    { label: "Available Now", value: "28+" },
    { label: "Coming Soon", value: "9+" }
  ],
  groups: [
    {
      title: "AI Clipping",
      items: ["AI Highlight Detection", "Semantic Clip Selection", "Manual Clip Selection", "Fixed Duration Mode", "Raw Footage Mode"]
    },
    {
      title: "AI Editing",
      items: ["Faster Whisper Transcription", "Styled Captions", "Roman Urdu/Hindi/Punjabi Workflow", "Auto Reframe", "Talking Head Reframe"]
    },
    {
      title: "Content Assets",
      items: ["Thumbnail Generator", "Metadata Generator", "Titles", "Hooks", "Hashtags", "CTA", "Music Categories"]
    },
    {
      title: "Workflow",
      items: ["Multiple Upload Methods", "Paste Link", "Local Project Videos", "Transcript Cache", "Progress Tracking", "Resume Job", "ZIP Export", "Creator Studio"]
    },
    {
      title: "Coming Soon",
      type: "soon",
      items: ["Publishing", "Scheduling", "Analytics", "Brand Kit", "Teams", "Cloud Storage", "API", "Google Drive", "Dropbox"]
    }
  ]
};

function createBenchmarkFeatureItem(text, type = "available") {
  const item = document.createElement("div");
  item.className = `benchmark-feature-item ${type}`;

  const marker = document.createElement("span");
  marker.className = "benchmark-feature-marker";
  marker.textContent = type === "missing" ? "No" : type === "limited" ? "Limited" : type === "soon" ? "Soon" : "";

  const label = document.createElement("span");
  label.textContent = text;

  item.append(marker, label);
  return item;
}

function createBenchmarkSummaryItem(label, value) {
  const item = document.createElement("div");
  item.className = "benchmark-summary-card";

  const valueNode = document.createElement("strong");
  valueNode.textContent = value;

  const labelNode = document.createElement("span");
  labelNode.textContent = label;

  item.append(valueNode, labelNode);
  return item;
}

function renderBenchmarkSummary(container, items) {
  if (!container) return;
  container.textContent = "";
  items.forEach((item) => container.appendChild(createBenchmarkSummaryItem(item.label, item.value)));
}

function renderBenchmarkGroup(container, title, items, type = "available") {
  const group = document.createElement("section");
  group.className = `benchmark-feature-group ${type}`;

  const header = document.createElement("div");
  header.className = "benchmark-group-head";

  const heading = document.createElement("h4");
  heading.className = "benchmark-group-title";
  heading.textContent = title;

  const count = document.createElement("span");
  count.className = "benchmark-group-count";
  count.textContent = String(items.length);

  const list = document.createElement("div");
  list.className = "benchmark-group-list";
  items.forEach((feature) => list.appendChild(createBenchmarkFeatureItem(feature, type)));

  header.append(heading, count);
  group.append(header, list);
  container.appendChild(group);
}

function renderClipforgeBenchmark(container, data) {
  if (!container) return;
  container.textContent = "";
  data.groups.forEach((group) => renderBenchmarkGroup(container, group.title, group.items, group.type || "available"));
}

function renderCompetitorBenchmark(container, data) {
  if (!container) return;
  container.textContent = "";
  renderBenchmarkGroup(container, "Available", data.available || [], "available");
  renderBenchmarkGroup(container, "Limited", data.limited || [], "limited");
  renderBenchmarkGroup(container, "Not Included", data.missing || [], "missing");
}

function renderBenchmarkWins(container, competitorName, wins) {
  if (!container) return;
  container.textContent = "";

  const title = document.createElement("h4");
  title.textContent = "Why ClipForge Wins";

  const list = document.createElement("div");
  list.className = "benchmark-wins-list";
  wins.forEach((win) => list.appendChild(createBenchmarkFeatureItem(win, "available")));

  const note = document.createElement("p");
  note.textContent = `Compared with ${competitorName}, ClipForge keeps more of the creator workflow in one place.`;

  container.append(title, list, note);
}

function setupBenchmarkComparison() {
  const section = document.querySelector(".benchmark-section");
  if (!section) return;

  const pills = Array.from(section.querySelectorAll("[data-benchmark-target]"));
  const card = document.getElementById("benchmarkCompetitorCard");
  const logo = document.getElementById("benchmarkCompetitorLogo");
  const name = document.getElementById("benchmarkCompetitorName");
  const description = document.getElementById("benchmarkCompetitorDescription");
  const competitorSummary = document.getElementById("benchmarkCompetitorSummary");
  const competitorFeatures = document.getElementById("benchmarkCompetitorFeatures");
  const clipforgeSummary = document.getElementById("benchmarkClipforgeSummary");
  const clipforgeFeatures = document.getElementById("benchmarkClipforgeFeatures");
  const wins = document.getElementById("benchmarkWins");

  renderBenchmarkSummary(clipforgeSummary, clipforgeBenchmarkFeatures.summary);
  renderClipforgeBenchmark(clipforgeFeatures, clipforgeBenchmarkFeatures);

  function selectCompetitor(key) {
    const data = benchmarkComparisonData[key] || benchmarkComparisonData.opusclip;
    card?.classList.add("is-switching");

    window.setTimeout(() => {
      if (logo) logo.textContent = data.logo;
      if (name) name.textContent = data.name;
      if (description) description.textContent = data.description;
      renderBenchmarkSummary(competitorSummary, [
        { label: "Competitor", value: data.name },
        { label: "Available Features", value: String((data.available || []).length) },
        { label: "Limited Features", value: String((data.limited || []).length) }
      ]);
      renderCompetitorBenchmark(competitorFeatures, data);
      renderBenchmarkWins(wins, data.name, data.wins || []);
      card?.classList.remove("is-switching");
    }, 140);

    pills.forEach((pill) => {
      const isActive = pill.dataset.benchmarkTarget === key;
      pill.classList.toggle("active", isActive);
      pill.setAttribute("aria-selected", String(isActive));
    });
  }

  pills.forEach((pill) => {
    pill.addEventListener("click", () => selectCompetitor(pill.dataset.benchmarkTarget));
  });

  selectCompetitor("opusclip");
}window.addEventListener("DOMContentLoaded", () => {
  setupThemeMode();
  setupCursorGlow();
  setupPageAnimations();
  setupBillingToggle();
  setupBenchmarkComparison();

  if (typeof setupResultTabs === "function") {
    setupResultTabs();
  }

  switchMode("upload");
  restorePreviousJobOnLoad();
});









