const state = {
  lessons: [],
  languages: [],
  user: null,
  authMode: "login",
  language: "en",
  progress: null,
  selectedLesson: null,
  currentCard: 0,
  categoryFilter: "All",
  quizCategory: "All",
  quizItems: [],
  quizIndex: 0,
  quizLocked: false,
  quizCorrect: 0,
  quizAnswers: [],
  view: "home",
};

const categories = ["All", "Vocabulary", "Travel", "Grammar"];
const categoryArt = { Vocabulary: ["✿", "mint"], Travel: ["↗", "peach"], Grammar: ["文", "lilac"] };
const byId = (id) => document.getElementById(id);

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new Error("Motiva cannot reach its server. Open the app at http://127.0.0.1:8000 while FastAPI is running.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Something went wrong. Please try again.");
  }
  return response.json();
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function showAuth(mode = state.authMode) {
  state.authMode = mode;
  byId("auth-screen").hidden = false;
  byId("app-shell").hidden = true;
  byId("auth-kicker").textContent = mode === "login" ? "WELCOME BACK" : "START YOUR LANGUAGE JOURNEY";
  byId("auth-title").textContent = mode === "login" ? "Sign in to Motiva" : "Create your account";
  byId("auth-subtitle").textContent = mode === "login" ? "Pick up where your learning left off." : "Your lessons and progress will be saved to your account.";
  byId("auth-submit").textContent = mode === "login" ? "Sign in" : "Create account";
  byId("auth-switch-line").innerHTML = mode === "login"
    ? 'New to Motiva? <button id="auth-switch" type="button">Create an account</button>'
    : 'Already have an account? <button id="auth-switch" type="button">Sign in</button>';
  byId("auth-switch").addEventListener("click", () => {
    showAuth(state.authMode === "login" ? "register" : "login");
  });
  byId("auth-message").textContent = "";
}

function showApp(user) {
  state.user = user;
  byId("auth-screen").hidden = true;
  byId("app-shell").hidden = false;
  byId("profile-name").textContent = user.username;
  byId("profile-avatar").textContent = user.username.charAt(0).toUpperCase();
  byId("top-avatar").textContent = user.username.charAt(0).toUpperCase();
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".view").forEach((panel) => panel.classList.toggle("active", panel.id === `view-${view}`));
  document.querySelectorAll(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  byId("breadcrumb-current").textContent = { home: "Overview", lessons: "My lessons", practice: "Practice quiz" }[view];
  byId("sidebar").classList.remove("open");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formatToday() {
  const now = new Date();
  byId("today-label").textContent = new Intl.DateTimeFormat("en", { weekday: "short", month: "short", day: "numeric" }).format(now);
  byId("daily-date").textContent = new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric" }).format(now);
}

function lessonCard(lesson) {
  const [icon, accent] = categoryArt[lesson.category] || ["✳", "mint"];
  return `<article class="lesson-card" data-lesson="${lesson.id}" tabindex="0" role="button" aria-label="Open ${lesson.title}">
    <div class="lesson-card-top"><span class="lesson-emoji ${accent}">${icon}</span><span class="lesson-level">${lesson.level}</span></div>
    <h3>${lesson.title}</h3><p>${lesson.description}</p>
    <div class="lesson-card-bottom"><span>${lesson.category} · ${lesson.item_count} cards</span><strong>Start →</strong></div>
  </article>`;
}

function renderLessons() {
  byId("home-lessons").innerHTML = state.lessons.slice(0, 3).map(lessonCard).join("");
  byId("all-lessons").innerHTML = state.lessons.filter((lesson) => state.categoryFilter === "All" || lesson.category === state.categoryFilter).map(lessonCard).join("");
  byId("category-filters").innerHTML = categories.map((category) => `<button class="filter-chip ${category === state.categoryFilter ? "active" : ""}" data-filter="${category}">${category}</button>`).join("");
}

function renderPersonalFocus(progress) {
  const personalization = progress.personalization || {};
  const focus = personalization.focus_lesson;
  const lesson = state.lessons.find((item) => item.id === focus?.id) || state.lessons[0];
  const completed = personalization.today_reviews || 0;
  const target = personalization.daily_goal || 5;
  const progressPercent = Math.min(100, Math.round((completed / target) * 100));
  const username = (state.user?.username || "Learner").replace(/[_-]+/g, " ");
  byId("welcome-title").textContent = `Welcome back, ${username}.`;
  byId("welcome-subheading").textContent = progress.reviewed
    ? (completed >= target ? "You have reached today's practice goal. Keep your rhythm going!" : `Your learning path is shaped by your answers. ${Math.max(0, target - completed)} more reviews to reach today's goal.`)
    : "Your personal learning path is ready. Start with a short lesson picked for you.";
  byId("daily-title").textContent = lesson ? lesson.title : "Your learning path starts here";
  byId("daily-description").textContent = focus?.reason || lesson?.description || "Create a lesson and add your first learning cards.";
  byId("daily-card-count").textContent = lesson ? `${lesson.item_count} cards · ${lesson.category}` : "Create your first lesson";
  byId("daily-goal-label").textContent = `${completed} / ${target} reviews`;
  byId("daily-goal-fill").style.width = `${progressPercent}%`;
  const startButton = byId("start-daily");
  if (lesson) {
    startButton.dataset.lesson = lesson.id;
    startButton.disabled = false;
  } else {
    delete startButton.dataset.lesson;
    startButton.disabled = true;
  }
}

function renderProgress() {
  const progress = state.progress || { reviewed: 0, accuracy: 0, streak: 0, weekly: [] };
  renderPersonalFocus(progress);
  byId("stat-reviewed").textContent = progress.reviewed;
  byId("stat-accuracy").textContent = progress.accuracy;
  byId("stat-streak").textContent = progress.streak;
  byId("sidebar-streak").textContent = `${progress.streak} day streak`;
  byId("accuracy-fill").style.width = `${progress.accuracy}%`;
  const weekly = progress.weekly || [];
  const max = Math.max(1, ...weekly.map((day) => day.total));
  byId("week-total").textContent = weekly.reduce((total, day) => total + day.total, 0);
  byId("weekly-chart").innerHTML = weekly.map((day) => {
    const value = day.total || 0;
    const label = new Intl.DateTimeFormat("en", { weekday: "short" }).format(new Date(`${day.date}T12:00:00`));
    const height = value ? Math.max(8, (value / max) * 100) : 2;
    return `<div class="chart-column ${day.date === new Date().toISOString().slice(0, 10) ? "today" : ""}" title="${value} reviews"><div class="chart-track"><div class="chart-bar" style="height:${height}%"></div></div><span>${label}</span></div>`;
  }).join("");
}

async function openLesson(id) {
  try {
    const lesson = await api(`/lessons/${id}`);
    state.selectedLesson = lesson;
    state.currentCard = 0;
    byId("flashcard-section").hidden = false;
    byId("flashcard-lesson-title").textContent = lesson.title;
    setView("lessons");
    renderFlashcard();
    byId("flashcard-section").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { showToast(error.message); }
}

function renderFlashcard() {
  const lesson = state.selectedLesson;
  if (!lesson) return;
  const personal = lesson.owner_id === state.user?.id;
  byId("personal-lesson-actions").hidden = !personal;
  if (!lesson.items?.length) {
    byId("card-counter").textContent = "YOUR PERSONAL LESSON";
    byId("flashcard-category").textContent = lesson.category.toUpperCase();
    byId("flash-term").textContent = "Your lesson is ready";
    byId("flash-pronunciation").textContent = "Add your first word or phrase below.";
    byId("flash-answer").hidden = true;
    byId("flash-example").hidden = true;
    byId("card-reveal").disabled = true;
    byId("card-prev").disabled = true;
    byId("card-next").disabled = true;
    byId("pronounce-word").disabled = true;
    return;
  }
  byId("card-reveal").disabled = false;
  byId("card-prev").disabled = false;
  byId("card-next").disabled = false;
  byId("pronounce-word").disabled = false;
  const item = lesson.items[state.currentCard];
  byId("card-counter").textContent = `CARD ${state.currentCard + 1} OF ${lesson.items.length}`;
  byId("flashcard-category").textContent = lesson.category.toUpperCase();
  byId("flash-term").textContent = item.term;
  byId("flash-pronunciation").textContent = item.pronunciation;
  byId("flash-answer").textContent = item.translation;
  byId("flash-example").textContent = `${item.example} · ${item.example_translation}`;
  byId("flash-answer").hidden = true;
  byId("flash-example").hidden = true;
  byId("card-reveal").textContent = "Show translation";
}

function speakWord() {
  const item = state.selectedLesson?.items[state.currentCard];
  if (!item || !("speechSynthesis" in window)) {
    showToast("Audio pronunciation is not available in this browser.");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(item.term);
  utterance.lang = state.language === "es" ? "es-ES" : "en-US";
  window.speechSynthesis.speak(utterance);
}

function revealCard() {
  const answer = byId("flash-answer");
  answer.hidden = !answer.hidden;
  byId("flash-example").hidden = answer.hidden;
  byId("card-reveal").textContent = answer.hidden ? "Show translation" : "Hide translation";
}

function renderQuizCategories() {
  const choices = ["All", ...new Set(state.lessons.map((lesson) => lesson.category))];
  byId("quiz-categories").innerHTML = choices.map((category) => {
    const count = category === "All" ? state.lessons.length : state.lessons.filter((lesson) => lesson.category === category).length;
    return `<button class="quiz-category ${category === state.quizCategory ? "active" : ""}" data-quiz-category="${category}">${category}<span>${count}</span></button>`;
  }).join("");
}

async function startQuiz() {
  try {
    const lessonGroups = await Promise.all(state.lessons.filter((lesson) => state.quizCategory === "All" || lesson.category === state.quizCategory).map((lesson) => api(`/lessons/${lesson.id}`)));
    state.quizItems = lessonGroups.flatMap((lesson) => lesson.items).sort(() => Math.random() - 0.5).slice(0, 8);
    state.quizIndex = 0;
    state.quizCorrect = 0;
    state.quizAnswers = [];
    state.quizLocked = false;
    renderQuizQuestion();
  } catch (error) { showToast(error.message); }
}

function gradeForPercent(percent) {
  if (percent >= 90) return { letter: "A", label: "Excellent work! You really know this set." };
  if (percent >= 80) return { letter: "B", label: "Great result! You are making strong progress." };
  if (percent >= 70) return { letter: "C", label: "Good work. A little more practice will make it stick." };
  if (percent >= 60) return { letter: "D", label: "You are getting there. Review the tricky answers and try again." };
  return { letter: "F", label: "Keep going. Every missed answer is a chance to learn." };
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function renderQuizQuestion() {
  const root = byId("quiz-main");
  if (!state.quizItems.length) {
    root.innerHTML = `<p class="quiz-empty">No cards are available yet.</p>`;
    return;
  }
  if (state.quizIndex >= state.quizItems.length) {
    const total = state.quizItems.length;
    const percent = Math.round((state.quizCorrect / total) * 100);
    const grade = gradeForPercent(percent);
    const missed = state.quizAnswers.filter((answer) => !answer.correct);
    const review = missed.length
      ? `<section class="quiz-review"><h3>Answers to review</h3>${missed.map((answer) => `<div class="quiz-review-row"><strong>${escapeHtml(answer.term)}</strong><span>Your answer: ${escapeHtml(answer.selected)}</span><b>Correct: ${escapeHtml(answer.translation)}</b></div>`).join("")}</section>`
      : `<p class="quiz-perfect-note">Perfect score — you got every answer right! ✨</p>`;
    root.innerHTML = `<div class="quiz-results"><p class="eyebrow">QUIZ COMPLETE</p><h2 class="quiz-question">Your result</h2><div class="quiz-grade-card"><div class="quiz-grade-letter">${grade.letter}</div><div class="quiz-grade-detail"><span>FINAL MARK</span><strong>${percent}%</strong><small>${state.quizCorrect} correct out of ${total}</small></div><div class="quiz-score-ring" style="--score:${percent}%"><span>${percent}<small>%</small></span></div></div><p class="quiz-grade-message">${grade.label}</p><div class="quiz-score-stats"><div><strong>${state.quizCorrect}</strong><span>Correct answers</span></div><div><strong>${total - state.quizCorrect}</strong><span>To review</span></div><div><strong>${total}</strong><span>Questions</span></div></div>${review}<button class="button button-primary" id="quiz-restart">Try another quiz</button></div>`;
    return;
  }
  const item = state.quizItems[state.quizIndex];
  const allItems = state.quizItems;
  const distractors = allItems.filter((candidate) => candidate.id !== item.id).sort(() => Math.random() - 0.5).slice(0, 3).map((candidate) => candidate.translation);
  const options = [...new Set([item.translation, ...distractors])].sort(() => Math.random() - 0.5);
  const answered = state.quizAnswers.length;
  const runningPercent = answered ? Math.round((state.quizCorrect / answered) * 100) : 0;
  const runningGrade = answered ? gradeForPercent(runningPercent).letter : "—";
  const progress = Math.round((state.quizIndex / state.quizItems.length) * 100);
  root.innerHTML = `<div class="quiz-progress-header"><p class="quiz-progress">QUESTION ${state.quizIndex + 1} <span>OF ${state.quizItems.length}</span></p><span class="quiz-running-mark">Mark so far: ${answered ? `${runningPercent}% (${runningGrade})` : "—"}</span></div><div class="quiz-progress-track"><span style="width:${progress}%"></span></div><h2 class="quiz-question">${escapeHtml(item.term)}</h2><p class="quiz-prompt">Choose the correct translation</p><div class="quiz-options">${options.map((option) => `<button class="quiz-option" data-answer="${encodeURIComponent(option)}">${escapeHtml(option)}</button>`).join("")}</div><div class="quiz-feedback" id="quiz-feedback" aria-live="polite"></div><button class="button button-primary quiz-next" id="quiz-next" hidden>${state.quizIndex + 1 === state.quizItems.length ? "See your mark" : "Next question →"}</button>`;
}
async function refreshLearningData() {
  [state.lessons, state.progress] = await Promise.all([
    api(`/lessons?language=${encodeURIComponent(state.language)}`),
    api(`/progress?language=${encodeURIComponent(state.language)}`),
  ]);
  renderLessons();
  renderProgress();
  renderQuizCategories();
}

async function createPersonalLesson(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  try {
    const lesson = await api("/lessons", {
      method: "POST",
      body: JSON.stringify({ ...values, language: state.language }),
    });
    form.reset();
    byId("create-lesson-form").hidden = true;
    await refreshLearningData();
    await openLesson(lesson.id);
    showToast("Your private lesson is ready");
  } catch (error) { showToast(error.message); }
}

async function createPersonalCard(event) {
  event.preventDefault();
  if (!state.selectedLesson) return;
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  try {
    await api(`/lessons/${state.selectedLesson.id}/items`, {
      method: "POST",
      body: JSON.stringify(values),
    });
    form.reset();
    byId("create-card-form").hidden = true;
    await openLesson(state.selectedLesson.id);
    await refreshLearningData();
    showToast("Card added to your lesson");
  } catch (error) { showToast(error.message); }
}

async function selectLanguage(code) {
  const language = state.languages.find((item) => item.code === code);
  if (!language || code === state.language) return;
  state.language = code;
  localStorage.setItem("motiva-language", code);
  state.categoryFilter = "All";
  state.quizCategory = "All";
  state.selectedLesson = null;
  byId("flashcard-section").hidden = true;
  try {
    await refreshLearningData();
    await startQuiz();
    showToast(`${language.name} lessons loaded`);
  } catch (error) { showToast(error.message); }
}

async function submitAnswer(button) {
  if (state.quizLocked) return;
  state.quizLocked = true;
  const item = state.quizItems[state.quizIndex];
  const selected = decodeURIComponent(button.dataset.answer);
  const correct = selected === item.translation;
  if (correct) state.quizCorrect += 1;
  state.quizAnswers.push({ term: item.term, translation: item.translation, selected, correct });
  document.querySelectorAll(".quiz-option").forEach((option) => {
    option.disabled = true;
    const answer = decodeURIComponent(option.dataset.answer);
    if (answer === item.translation) option.classList.add("correct");
    else if (option === button) option.classList.add("wrong");
  });
  const answered = state.quizAnswers.length;
  const mark = Math.round((state.quizCorrect / answered) * 100);
  const grade = gradeForPercent(mark).letter;
  byId("quiz-feedback").textContent = correct
    ? `Correct — +1 point. Your mark so far: ${mark}% (${grade}).`
    : `The correct answer is “${item.translation}”. Your mark so far: ${mark}% (${grade}).`;
  byId("quiz-next").hidden = false;
  try {
    await api("/progress/reviews", { method: "POST", body: JSON.stringify({ item_id: item.id, correct }) });
    state.progress = await api(`/progress?language=${encodeURIComponent(state.language)}`);
    renderProgress();
  } catch (error) { showToast(error.message); }
}

function bindEvents() {
  document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.go)));
  byId("menu-toggle").addEventListener("click", () => byId("sidebar").classList.toggle("open"));
  byId("language-select").addEventListener("change", (event) => {
    const selected = state.languages.find((item) => item.code === event.target.value);
    if (selected) byId("course-flag").textContent = selected.flag;
    selectLanguage(event.target.value);
  });
  byId("auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    values.username = String(values.username || "").trim();
    const usernameInput = event.currentTarget.elements.username;
    const passwordInput = event.currentTarget.elements.password;
    const message = byId("auth-message");
    if (!/^[A-Za-z0-9_]{3,24}$/.test(values.username)) {
      message.textContent = "Username must be 3–24 characters and use only letters, numbers, or underscores.";
      usernameInput.focus();
      return;
    }
    if (String(values.password || "").length < 8) {
      message.textContent = "Password must be at least 8 characters long.";
      passwordInput.focus();
      return;
    }
    const endpoint = state.authMode === "login" ? "/auth/login" : "/auth/register";
    const submitButton = byId("auth-submit");
    const originalLabel = state.authMode === "login" ? "Sign in" : "Create account";
    submitButton.disabled = true;
    submitButton.textContent = state.authMode === "login" ? "Signing in…" : "Creating account…";
    byId("auth-message").textContent = "";
    try {
      const user = await api(endpoint, { method: "POST", body: JSON.stringify(values) });
      showApp(user);
      await loadLearningApp();
    } catch (error) {
      byId("auth-message").textContent = error.message;
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
    }
  });
  byId("account-logout").addEventListener("click", async () => {
    try { await api("/auth/logout", { method: "POST" }); }
    finally { window.location.reload(); }
  });
  byId("open-create-lesson").addEventListener("click", () => { byId("create-lesson-form").hidden = false; });
  byId("close-create-lesson").addEventListener("click", () => { byId("create-lesson-form").hidden = true; });
  byId("create-lesson-form").addEventListener("submit", createPersonalLesson);
  byId("open-create-card").addEventListener("click", () => { byId("create-card-form").hidden = false; });
  byId("close-create-card").addEventListener("click", () => { byId("create-card-form").hidden = true; });
  byId("create-card-form").addEventListener("submit", createPersonalCard);
  document.addEventListener("click", (event) => {
    const card = event.target.closest("[data-lesson]");
    if (card) openLesson(card.dataset.lesson);
    const filter = event.target.closest("[data-filter]");
    if (filter) { state.categoryFilter = filter.dataset.filter; renderLessons(); }
    const category = event.target.closest("[data-quiz-category]");
    if (category) { state.quizCategory = category.dataset.quizCategory; renderQuizCategories(); startQuiz(); }
    const option = event.target.closest("[data-answer]");
    if (option) submitAnswer(option);
    if (event.target.closest("#quiz-next")) { state.quizIndex += 1; state.quizLocked = false; renderQuizQuestion(); }
    if (event.target.closest("#quiz-restart")) startQuiz();
  });
  byId("flashcard").addEventListener("click", revealCard);
  byId("card-reveal").addEventListener("click", revealCard);
  byId("pronounce-word").addEventListener("click", speakWord);
  byId("card-prev").addEventListener("click", () => { if (!state.selectedLesson) return; state.currentCard = (state.currentCard - 1 + state.selectedLesson.items.length) % state.selectedLesson.items.length; renderFlashcard(); });
  byId("card-next").addEventListener("click", () => { if (!state.selectedLesson) return; state.currentCard = (state.currentCard + 1) % state.selectedLesson.items.length; renderFlashcard(); });
  byId("close-flashcards").addEventListener("click", () => { byId("flashcard-section").hidden = true; });
}

async function loadLearningApp() {
  state.languages = await api("/languages");
  const savedLanguage = localStorage.getItem("motiva-language");
  state.language = state.languages.some((item) => item.code === savedLanguage) ? savedLanguage : "en";
  byId("language-select").innerHTML = state.languages.map((item) => `<option value="${item.code}">${item.name}</option>`).join("");
  byId("language-select").value = state.language;
  const activeLanguage = state.languages.find((item) => item.code === state.language);
  byId("course-flag").textContent = activeLanguage.flag;
  await refreshLearningData();
  await startQuiz();
}

async function initialize() {
  formatToday();
  showAuth("login");
  bindEvents();
  try {
    const user = await api("/auth/me");
    showApp(user);
    await loadLearningApp();
  } catch (error) {
    showAuth("login");
    if (error.message !== "Please sign in to continue" && !error.message.includes("session has expired")) {
      byId("auth-message").textContent = "Cannot reach the learning server. Start FastAPI and try again.";
    }
  }
}

initialize();
