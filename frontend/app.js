const state = {
  lessons: [],
  languages: [],
  user: null,
  authMode: "login",
  language: "en",
  progress: null,
  weekStart: null,
  selectedLesson: null,
  currentCard: 0,
  currentCardReviewed: false,
  pendingProfilePhoto: null,
  categoryFilter: "All",
  levelFilter: "All",
  quizCategory: "All",
  quizLevel: "All",
  quizLessonId: null,
  quizItems: [],
  quizSessionId: null,
  quizDeadline: null,
  quizTimer: null,
  quizTimedOut: false,
  savedQuizResult: null,
  quizIndex: 0,
  quizLocked: false,
  quizCorrect: 0,
  quizAnswers: [],
  view: "home",
  adminOverview: null,
  adminLearners: [],
  selectedAdminLearnerId: null,
  adminLessons: [],
  adminLesson: null,
};

const categories = ["All", "Vocabulary", "Travel", "Grammar"];
const levels = ["All", "Beginner", "Intermediate", "Advanced"];
const categoryArt = { Vocabulary: ["✿", "mint"], Travel: ["↗", "peach"], Grammar: ["文", "lilac"] };
const byId = (id) => document.getElementById(id);

function setTheme(theme, persist = true) {
  const selected = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = selected;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", selected === "dark" ? "#101916" : "#f4f7f3");
  document.querySelectorAll(".theme-toggle").forEach((button) => {
    const dark = selected === "dark";
    button.setAttribute("aria-label", `Switch to ${dark ? "light" : "dark"} mode`);
    button.title = `Switch to ${dark ? "light" : "dark"} mode`;
    button.querySelector(".theme-icon").textContent = dark ? "☀" : "☾";
    button.querySelector(".theme-label").textContent = dark ? "Light mode" : "Dark mode";
  });
  if (persist) localStorage.setItem("motiva-theme", selected);
}

function toggleTheme() {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

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

function setAvatar(element, user) {
  element.replaceChildren();
  if (user?.profile_image) {
    const image = document.createElement("img");
    image.src = user.profile_image;
    image.alt = "";
    element.append(image);
  } else {
    element.textContent = (user?.username || "Learner").charAt(0).toUpperCase();
  }
}

function renderProfilePhotoPreview(photo = state.pendingProfilePhoto ?? state.user?.profile_image) {
  const preview = byId("profile-photo-preview");
  preview.replaceChildren();
  if (photo) {
    const image = document.createElement("img");
    image.src = photo;
    image.alt = "Profile photo preview";
    preview.append(image);
  } else {
    preview.textContent = (state.user?.username || "Learner").charAt(0).toUpperCase();
  }
}

function openProfileDialog() {
  state.pendingProfilePhoto = null;
  byId("profile-photo-file").value = "";
  byId("profile-photo-error").textContent = "";
  byId("save-profile-photo").disabled = true;
  byId("remove-profile-photo").hidden = !state.user?.profile_image;
  renderProfilePhotoPreview(state.user?.profile_image || null);
  byId("profile-dialog").showModal();
}

function readProfilePhoto(file) {
  const supportedTypes = ["image/png", "image/jpeg", "image/webp"];
  if (!supportedTypes.includes(file.type)) {
    state.pendingProfilePhoto = null;
    byId("save-profile-photo").disabled = true;
    renderProfilePhotoPreview(state.user?.profile_image || null);
    byId("profile-photo-error").textContent = "Choose a PNG, JPEG, or WebP image.";
    byId("profile-photo-file").value = "";
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    state.pendingProfilePhoto = null;
    byId("save-profile-photo").disabled = true;
    renderProfilePhotoPreview(state.user?.profile_image || null);
    byId("profile-photo-error").textContent = "This photo is larger than 2 MB. Choose a smaller image.";
    byId("profile-photo-file").value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    state.pendingProfilePhoto = String(reader.result);
    byId("profile-photo-error").textContent = "";
    byId("save-profile-photo").disabled = false;
    renderProfilePhotoPreview(state.pendingProfilePhoto);
  };
  reader.onerror = () => {
    state.pendingProfilePhoto = null;
    byId("save-profile-photo").disabled = true;
    renderProfilePhotoPreview(state.user?.profile_image || null);
    byId("profile-photo-error").textContent = "The selected photo could not be read.";
  };
  reader.readAsDataURL(file);
}

async function saveProfilePhoto(event) {
  event.preventDefault();
  if (!state.pendingProfilePhoto) return;
  const button = byId("save-profile-photo");
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const result = await api("/profile/photo", {
      method: "PUT",
      body: JSON.stringify({ data_url: state.pendingProfilePhoto }),
    });
    state.user.profile_image = result.profile_image;
    setAvatar(byId("profile-avatar"), state.user);
    setAvatar(byId("top-avatar"), state.user);
    byId("profile-dialog").close();
    showToast("Profile photo saved to your account");
  } catch (error) {
    byId("profile-photo-error").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Save photo";
  }
}

async function removeProfilePhoto() {
  const button = byId("remove-profile-photo");
  button.disabled = true;
  try {
    await api("/profile/photo", { method: "DELETE" });
    state.user.profile_image = null;
    state.pendingProfilePhoto = null;
    setAvatar(byId("profile-avatar"), state.user);
    setAvatar(byId("top-avatar"), state.user);
    byId("profile-dialog").close();
    showToast("Profile photo removed");
  } catch (error) {
    byId("profile-photo-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
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
  setAvatar(byId("profile-avatar"), user);
  setAvatar(byId("top-avatar"), user);
  byId("admin-nav").hidden = user.role !== "admin";
  if (user.role === "admin") loadAdminStudio();
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".view").forEach((panel) => panel.classList.toggle("active", panel.id === `view-${view}`));
  document.querySelectorAll(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  byId("breadcrumb-current").textContent = { home: "Overview", lessons: "Course library", practice: "Practice quiz", admin: "Admin studio" }[view];
  byId("sidebar").classList.remove("open");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formatToday() {
  const now = new Date();
  byId("today-label").textContent = new Intl.DateTimeFormat("en", { weekday: "short", month: "short", day: "numeric" }).format(now);
  byId("daily-date").textContent = new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric" }).format(now);
}

function localDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function mondayOf(date) {
  const monday = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return monday;
}

function currentWeekStart() {
  return localDateKey(mondayOf(new Date()));
}

function stopQuizTimer() {
  if (state.quizTimer) window.clearInterval(state.quizTimer);
  state.quizTimer = null;
}

function renderQuizTimer() {
  const timer = byId("quiz-timer");
  if (!timer || !state.quizDeadline) return;
  const remaining = Math.max(0, Math.ceil((state.quizDeadline - performance.now()) / 1000));
  const minutes = Math.floor(remaining / 60).toString().padStart(2, "0");
  const seconds = (remaining % 60).toString().padStart(2, "0");
  timer.textContent = `${minutes}:${seconds}`;
  timer.classList.toggle("urgent", remaining <= 10);
  timer.setAttribute("aria-label", `${minutes} minutes ${seconds} seconds remaining`);
  if (remaining === 0) {
    stopQuizTimer();
    expireCurrentQuiz();
  }
}

async function expireCurrentQuiz() {
  if (!state.quizSessionId || state.savedQuizResult || state.quizTimedOut) return;
  state.quizLocked = true;
  state.quizTimedOut = true;
  document.querySelectorAll(".quiz-option").forEach((option) => { option.disabled = true; });
  try {
    const result = await api("/quiz/expire", {
      method: "POST",
      body: JSON.stringify({ session_id: state.quizSessionId }),
    });
    state.quizCorrect = result.correct_count;
    state.savedQuizResult = result;
    state.quizIndex = state.quizItems.length;
    renderQuizQuestion();
    await refreshLearningData();
  } catch (error) {
    state.quizTimedOut = false;
    state.quizLocked = false;
    showToast(error.message);
    state.quizTimer = window.setInterval(renderQuizTimer, 1000);
  }
}

function lessonCard(lesson) {
  const [icon, accent] = categoryArt[lesson.category] || ["✳", "mint"];
  const quizSummary = lesson.quiz_answers
    ? `${lesson.quiz_answers} quiz answers · ${lesson.quiz_accuracy}% accuracy`
    : "No quiz answers yet";
  return `<article class="lesson-card" data-lesson="${escapeHtml(lesson.id)}" tabindex="0" role="button" aria-label="Open ${escapeHtml(lesson.title)}">
    <div class="lesson-card-top"><span class="lesson-emoji ${accent}">${icon}</span><span class="lesson-level">${escapeHtml(lesson.level)}</span></div>
    <h3>${escapeHtml(lesson.title)}</h3><p>${escapeHtml(lesson.description)}</p>
    <div class="lesson-study-progress"><div><span>Flashcard progress</span><strong>${lesson.cards_studied}/${lesson.item_count}</strong></div><div class="lesson-progress-track"><span style="width:${lesson.study_percent}%"></span></div><small>${lesson.study_percent}% of cards studied</small></div>
    <div class="lesson-card-bottom"><span>${escapeHtml(lesson.category)} · ${lesson.item_count} cards</span><strong>Study →</strong></div><div class="lesson-quiz-summary">${quizSummary}</div>
  </article>`;
}

function renderLessons() {
  byId("home-lessons").innerHTML = state.lessons.slice(0, 3).map(lessonCard).join("");
  const filtered = state.lessons.filter((lesson) =>
    state.categoryFilter === "All" || lesson.category === state.categoryFilter,
  );
  const visibleLevels = state.levelFilter === "All"
    ? levels.slice(1).filter((level) => filtered.some((lesson) => lesson.level === level))
    : [state.levelFilter];
  byId("all-lessons").innerHTML = visibleLevels.map((level) => {
    const group = filtered.filter((lesson) => lesson.level === level);
    if (!group.length) return "";
    return `<section class="course-level-group"><header><div><p class="eyebrow">DIFFICULTY</p><h2>${escapeHtml(level)}</h2></div><span>${group.length} ${group.length === 1 ? "course" : "courses"}</span></header><div class="lesson-grid lesson-grid-large">${group.map(lessonCard).join("")}</div></section>`;
  }).join("") || `<p class="course-empty">No courses at this level yet. Check back when your administrator adds one.</p>`;
  byId("category-filters").innerHTML = categories.map((category) => `<button class="filter-chip ${category === state.categoryFilter ? "active" : ""}" data-filter="${category}">${category}</button>`).join("");
  byId("level-filters").innerHTML = levels.map((level) => `<button class="filter-chip ${level === state.levelFilter ? "active" : ""}" data-level-filter="${level}">${level === "All" ? "All levels" : escapeHtml(level)}</button>`).join("");
}

async function loadAdminStudio(selectId = state.adminLesson?.id) {
  if (state.user?.role !== "admin") return;
  try {
    [state.adminOverview, state.adminLessons, state.adminLearners] = await Promise.all([
      api("/admin/overview"),
      api("/admin/lessons"),
      api("/admin/learners"),
    ]);
    renderAdminOverview();
    renderAdminLessonList();
    renderAdminLearners();
    if (selectId && state.adminLessons.some((lesson) => lesson.id === selectId)) {
      await selectAdminLesson(selectId);
    } else {
      state.adminLesson = null;
      byId("admin-editor").hidden = true;
      byId("admin-empty").hidden = false;
    }
  } catch (error) { showToast(error.message); }
}

function renderAdminOverview() {
  const overview = state.adminOverview || {};
  byId("admin-stat-lessons").textContent = overview.lessons || 0;
  byId("admin-stat-cards").textContent = overview.cards || 0;
  byId("admin-stat-questions").textContent = overview.questions || 0;
  byId("admin-stat-attempts").textContent = overview.attempts || 0;
}

function renderAdminLearners() {
  const root = byId("admin-learner-list");
  root.innerHTML = state.adminLearners.map((learner) => `
    <button class="admin-learner-choice ${state.selectedAdminLearnerId === learner.id ? "active" : ""}" type="button" data-admin-learner="${learner.id}">
      <span class="learner-avatar">${escapeHtml(learner.username.charAt(0).toUpperCase())}</span>
      <span class="learner-choice-copy"><strong>${escapeHtml(learner.username)}</strong><small>${learner.activity_count} saved study actions</small></span>
      <span class="learner-choice-arrow">→</span>
    </button>`).join("") || `<p class="admin-empty-note">No learner accounts have registered yet.</p>`;
  renderAdminLearnerDetail(state.selectedAdminLearnerId);
}

function renderAdminLearnerDetail(learnerId) {
  const learner = state.adminLearners.find((item) => item.id === Number(learnerId));
  if (!learner) {
    state.selectedAdminLearnerId = null;
    byId("admin-learner-detail").innerHTML = `<div class="admin-empty"><span>✦</span><h2>Select a learner</h2><p>Review course activity, flashcard coverage, and quiz accuracy.</p></div>`;
    return;
  }
  state.selectedAdminLearnerId = learner.id;
  const totalCardsStudied = learner.courses.reduce((sum, course) => sum + course.cards_studied, 0);
  const totalQuizAnswers = learner.courses.reduce((sum, course) => sum + course.quiz_answers, 0);
  const lastActivity = learner.last_activity
    ? new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(learner.last_activity))
    : "No study activity yet";
  byId("admin-learner-detail").innerHTML = `<div class="learner-detail-header"><span class="learner-avatar large">${escapeHtml(learner.username.charAt(0).toUpperCase())}</span><div><p class="eyebrow">LEARNER PROFILE</p><h3>${escapeHtml(learner.username)}</h3><small>Last activity: ${escapeHtml(lastActivity)}</small></div></div><div class="learner-detail-stats"><article><strong>${totalCardsStudied}</strong><span>Cards studied</span></article><article><strong>${totalQuizAnswers}</strong><span>Quiz answers</span></article><article><strong>${learner.courses.filter((course) => course.cards_studied > 0 || course.quiz_answers > 0).length}</strong><span>Courses started</span></article></div><div class="learner-course-progress">${learner.courses.map((course) => `<article class="learner-course-row"><div class="learner-course-heading"><div><span>${escapeHtml(course.language.toUpperCase())} · ${escapeHtml(course.level)} · ${escapeHtml(course.category)}</span><strong>${escapeHtml(course.title)}</strong></div><b>${course.study_percent}%</b></div><div class="lesson-progress-track"><span style="width:${course.study_percent}%"></span></div><div class="learner-course-metrics"><span>${course.cards_studied}/${course.item_count} cards rated</span><span>${course.quiz_answers ? `${course.quiz_answers} quiz answers · ${course.quiz_accuracy}% accuracy` : "No quiz attempts"}</span></div></article>`).join("")}</div>`;
  document.querySelectorAll("[data-admin-learner]").forEach((button) => button.classList.toggle("active", Number(button.dataset.adminLearner) === learner.id));
}

function renderAdminLessonList() {
  const root = byId("admin-lesson-list");
  root.innerHTML = state.adminLessons.map((lesson) => `
    <button class="admin-lesson-choice ${state.adminLesson?.id === lesson.id ? "active" : ""}" type="button" data-admin-lesson="${escapeHtml(lesson.id)}">
      <span class="admin-lesson-language">${lesson.language === "es" ? "🇪🇸 ES" : "🇬🇧 EN"} · ${escapeHtml(lesson.category)}</span>
      <strong>${escapeHtml(lesson.title)}</strong>
      <small>${lesson.item_count} cards · ${lesson.question_count} questions</small>
    </button>`).join("") || `<p class="admin-empty-note">No shared lessons yet. Create the first one above.</p>`;
}

async function selectAdminLesson(id) {
  try {
    state.adminLesson = await api(`/admin/lessons/${encodeURIComponent(id)}`);
    byId("admin-empty").hidden = true;
    byId("admin-editor").hidden = false;
    fillAdminLessonEditor();
    renderAdminLessonList();
  } catch (error) { showToast(error.message); }
}

function fillAdminLessonEditor() {
  const lesson = state.adminLesson;
  if (!lesson) return;
  const form = byId("admin-edit-lesson-form");
  for (const key of ["id", "title", "level", "language", "category", "description"]) {
    form.elements[key].value = lesson[key];
  }
  byId("admin-edit-title").textContent = lesson.title;
  renderAdminCards();
  renderAdminQuestions();
}

function renderAdminCards() {
  const root = byId("admin-card-list");
  root.innerHTML = (state.adminLesson?.items || []).map((card) => `
    <article class="admin-record">
      <div class="admin-record-copy"><strong>${escapeHtml(card.term)}</strong><span>${escapeHtml(card.translation)}</span><small><b>Pronunciation:</b> ${escapeHtml(card.pronunciation)}</small><small><b>Example:</b> ${escapeHtml(card.example)}</small><small><b>Example translation:</b> ${escapeHtml(card.example_translation)}</small></div>
      <div class="admin-record-actions"><button type="button" data-admin-action="edit-card" data-id="${card.id}" aria-label="Edit card">Edit</button><button type="button" class="danger-text" data-admin-action="delete-card" data-id="${card.id}" aria-label="Delete card">Delete</button></div>
    </article>`).join("") || `<p class="admin-empty-note">No cards in this lesson yet.</p>`;
}

function renderAdminQuestions() {
  const root = byId("admin-question-list");
  root.innerHTML = (state.adminLesson?.quiz_questions || []).map((question) => {
    const generated = question.question_type !== "custom";
    const choices = question.choices.map((choice) => {
      const correct = choice === question.correct_answer;
      return `<li class="${correct ? "correct" : ""}">${escapeHtml(choice)}${correct ? `<b>Correct answer</b>` : ""}</li>`;
    }).join("");
    return `<article class="admin-record">
      <div class="admin-record-copy"><strong>${escapeHtml(question.prompt)}</strong><span>${generated ? `Auto-generated · ${escapeHtml(question.level)}` : `Administrator-created · ${escapeHtml(question.level)}`}</span><ol class="admin-choice-list">${choices}</ol><small><b>Explanation:</b> ${escapeHtml(question.explanation)}</small>${generated ? `<small>This question follows its source flashcard. Edit that card to change the question or its answer.</small>` : ""}</div>
      ${generated
        ? `<div class="admin-record-actions"><button type="button" data-admin-action="edit-card" data-id="${question.source_item_id}" ${question.source_item_id == null ? "disabled" : ""}>Edit source card</button></div>`
        : `<div class="admin-record-actions"><button type="button" data-admin-action="edit-question" data-id="${question.id}">Edit</button><button type="button" class="danger-text" data-admin-action="delete-question" data-id="${question.id}">Delete</button></div>`}
    </article>`;
  }).join("") || `<p class="admin-empty-note">No quiz questions yet. Questions are generated from cards or can be written below.</p>`;
}

function beginEditCard(id) {
  const card = state.adminLesson?.items.find((item) => item.id === Number(id));
  if (!card) return;
  const form = byId("admin-card-form");
  form.elements.id.value = card.id;
  for (const key of ["term", "translation", "pronunciation", "example", "example_translation"]) {
    form.elements[key].value = card[key];
  }
  byId("admin-card-submit").textContent = "Save card";
  byId("admin-card-cancel").hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetAdminCardForm() {
  byId("admin-card-form").reset();
  byId("admin-card-form").elements.id.value = "";
  byId("admin-card-submit").textContent = "＋ Add card";
  byId("admin-card-cancel").hidden = true;
}

function updateCorrectAnswerChoices(selectedValue = "") {
  const form = byId("admin-quiz-form");
  const select = form.elements.correct_answer;
  const options = ["choice_a", "choice_b", "choice_c", "choice_d"]
    .map((key) => form.elements[key].value.trim()).filter(Boolean);
  select.innerHTML = `<option value="">Choose the correct choice</option>${[...new Set(options)].map((choice) => `<option value="${escapeHtml(choice)}">${escapeHtml(choice)}</option>`).join("")}`;
  select.value = selectedValue;
}

function beginEditQuestion(id) {
  const question = state.adminLesson?.quiz_questions.find((item) => item.id === Number(id));
  if (!question || question.question_type !== "custom") return;
  const form = byId("admin-quiz-form");
  form.elements.id.value = question.id;
  form.elements.prompt.value = question.prompt;
  form.elements.level.value = question.level;
  form.elements.explanation.value = question.explanation;
  ["choice_a", "choice_b", "choice_c", "choice_d"].forEach((key, index) => {
    form.elements[key].value = question.choices[index] || "";
  });
  updateCorrectAnswerChoices(question.correct_answer);
  byId("admin-quiz-submit").textContent = "Save question";
  byId("admin-quiz-cancel").hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetAdminQuestionForm() {
  byId("admin-quiz-form").reset();
  byId("admin-quiz-form").elements.id.value = "";
  updateCorrectAnswerChoices();
  byId("admin-quiz-submit").textContent = "＋ Add question";
  byId("admin-quiz-cancel").hidden = true;
}

async function handleAdminAction(action, id) {
  if (!state.adminLesson) return;
  if (action === "edit-card") return beginEditCard(id);
  if (action === "edit-question") return beginEditQuestion(id);
  const message = action === "delete-card" ? "Delete this flashcard?" : "Delete this custom quiz question?";
  if (!window.confirm(message)) return;
  try {
    const path = action === "delete-card" ? `/admin/items/${id}` : `/admin/quiz-questions/${id}`;
    await api(path, { method: "DELETE" });
    await loadAdminStudio(state.adminLesson.id);
    await refreshLearningData();
    showToast(action === "delete-card" ? "Card deleted" : "Quiz question deleted");
  } catch (error) { showToast(error.message); }
}

function bindAdminEvents() {
  byId("admin-create-lesson-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    try {
      const lesson = await api("/admin/lessons", { method: "POST", body: JSON.stringify(values) });
      form.reset();
      await loadAdminStudio(lesson.id);
      showToast("Shared lesson saved to the database");
    } catch (error) { showToast(error.message); }
  });

  byId("admin-edit-lesson-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const id = values.id;
    delete values.id;
    try {
      await api(`/admin/lessons/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(values) });
      await loadAdminStudio(id);
      await refreshLearningData();
      showToast("Lesson changes saved");
    } catch (error) { showToast(error.message); }
  });

  byId("admin-delete-lesson").addEventListener("click", async () => {
    const lesson = state.adminLesson;
    if (!lesson || !window.confirm(`Delete “${lesson.title}” and its cards and questions?`)) return;
    try {
      await api(`/admin/lessons/${encodeURIComponent(lesson.id)}`, { method: "DELETE" });
      state.adminLesson = null;
      await loadAdminStudio(null);
      await refreshLearningData();
      showToast("Lesson deleted");
    } catch (error) { showToast(error.message); }
  });

  byId("admin-card-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.adminLesson) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const id = values.id;
    delete values.id;
    try {
      const path = id
        ? `/admin/items/${id}`
        : `/admin/lessons/${encodeURIComponent(state.adminLesson.id)}/items`;
      await api(path, { method: id ? "PUT" : "POST", body: JSON.stringify(values) });
      resetAdminCardForm();
      await loadAdminStudio(state.adminLesson.id);
      await refreshLearningData();
      showToast(id ? "Card updated" : "Card and quiz questions saved");
    } catch (error) { showToast(error.message); }
  });

  byId("admin-quiz-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.adminLesson) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const id = values.id;
    const payload = {
      lesson_id: state.adminLesson.id,
      prompt: values.prompt,
      choices: [values.choice_a, values.choice_b, values.choice_c, values.choice_d].map((choice) => choice.trim()).filter(Boolean),
      correct_answer: values.correct_answer,
      explanation: values.explanation,
      level: values.level,
    };
    try {
      const path = id ? `/admin/quiz-questions/${id}` : "/admin/quiz-questions";
      await api(path, { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
      resetAdminQuestionForm();
      await loadAdminStudio(state.adminLesson.id);
      await refreshLearningData();
      showToast(id ? "Quiz question updated" : "Quiz question saved");
    } catch (error) { showToast(error.message); }
  });

  ["choice_a", "choice_b", "choice_c", "choice_d"].forEach((key) => {
    byId("admin-quiz-form").elements[key].addEventListener("input", () => updateCorrectAnswerChoices());
  });
  byId("admin-card-cancel").addEventListener("click", resetAdminCardForm);
  byId("admin-quiz-cancel").addEventListener("click", resetAdminQuestionForm);
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
  byId("daily-description").textContent = focus?.reason || lesson?.description || "Choose a lesson from the shared course library to begin.";
  byId("daily-card-count").textContent = lesson ? `${lesson.item_count} cards · ${lesson.category}` : "Shared lessons are managed by your administrator";
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
  byId("stat-streak-unit").textContent = progress.streak === 1 ? " day" : " days";
  byId("sidebar-streak").textContent = `${progress.streak} ${progress.streak === 1 ? "day" : "days"} streak`;
  byId("streak-status").textContent = progress.streak_active_today
    ? "Today's study or quiz activity is counted."
    : progress.streak
      ? "Study today to keep your streak active."
      : "Study a card or answer a quiz to begin.";
  byId("accuracy-fill").style.width = `${progress.accuracy}%`;
  const weekly = progress.weekly || [];
  const max = Math.max(1, ...weekly.map((day) => day.total));
  const todayKey = localDateKey(new Date());
  const weekStart = progress.week_start || state.weekStart || currentWeekStart();
  const weekEnd = progress.week_end || weekStart;
  const weekStartDate = new Date(`${weekStart}T12:00:00`);
  const weekEndDate = new Date(`${weekEnd}T12:00:00`);
  const startLabel = new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(weekStartDate);
  const endLabel = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(weekEndDate);
  byId("week-label").textContent = `${startLabel} – ${endLabel}`;
  byId("week-previous").disabled = false;
  byId("week-next").disabled = weekStart >= currentWeekStart();
  byId("week-total").textContent = weekly.reduce((total, day) => total + day.total, 0);
  byId("weekly-chart").innerHTML = weekly.map((day) => {
    const value = day.total || 0;
    const label = new Intl.DateTimeFormat("en", { weekday: "short" }).format(new Date(`${day.date}T12:00:00`));
    const height = value ? Math.max(8, (value / max) * 100) : 2;
    return `<div class="chart-column ${day.date === todayKey ? "today" : ""}" title="${value} learning actions"><div class="chart-track"><div class="chart-bar" style="height:${height}%"></div></div><span>${label}</span></div>`;
  }).join("");
  const quizDays = progress.weekly_quizzes || [];
  const quizAverage = progress.weekly_quiz_average;
  byId("quiz-week-average").textContent = quizAverage == null ? "—" : `${quizAverage}%`;
  byId("quiz-week-count").textContent = `${progress.weekly_quiz_count || 0} completed ${progress.weekly_quiz_count === 1 ? "quiz" : "quizzes"}`;
  byId("quiz-weekly-chart").innerHTML = quizDays.map((day) => {
    const label = new Intl.DateTimeFormat("en", { weekday: "short" }).format(new Date(`${day.date}T12:00:00`));
    const score = day.quiz_average;
    const height = score == null ? 2 : Math.max(8, score);
    const title = score == null ? "No completed quiz" : `${day.quiz_count} ${day.quiz_count === 1 ? "quiz" : "quizzes"} · average ${score}%`;
    return `<div class="chart-column ${day.date === todayKey ? "today" : ""}" title="${title}"><div class="chart-track"><div class="quiz-chart-bar" style="height:${height}%"></div></div><span>${label}</span>${score == null ? "" : `<small>${score}%</small>`}</div>`;
  }).join("");
  byId("quiz-week-empty").hidden = Boolean(progress.weekly_quiz_count);
}

async function openLesson(id) {
  try {
    const lesson = await api(`/lessons/${id}`);
    state.selectedLesson = lesson;
    state.currentCard = 0;
    byId("flashcard-section").hidden = false;
    byId("flashcard-lesson-title").textContent = lesson.title;
    renderCourseProgressDetail();
    setView("lessons");
    renderFlashcard();
    byId("flashcard-section").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { showToast(error.message); }
}

function renderCourseProgressDetail() {
  const lesson = state.lessons.find((item) => item.id === state.selectedLesson?.id);
  if (!lesson) {
    byId("course-progress-detail").textContent = "";
    return;
  }
  const quizProgress = lesson.quiz_answers
    ? `${lesson.quiz_answers} quiz answers · ${lesson.quiz_accuracy}% accuracy`
    : "No quiz attempts yet";
  byId("course-progress-detail").textContent = `${lesson.cards_studied}/${lesson.item_count} flashcards studied · ${quizProgress}`;
}

function renderFlashcard() {
  const lesson = state.selectedLesson;
  if (!lesson) return;
  state.currentCardReviewed = false;
  byId("card-review-actions").hidden = true;
  byId("card-review-message").textContent = "";
  document.querySelectorAll("[data-card-review]").forEach((button) => { button.disabled = false; });
  if (!lesson.items?.length) {
    byId("card-counter").textContent = "LESSON CONTENT";
    byId("flashcard-category").textContent = lesson.category.toUpperCase();
    byId("flash-term").textContent = "This lesson is being prepared";
    byId("flash-pronunciation").textContent = "Please check back after new cards are added.";
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
  byId("card-review-actions").hidden = answer.hidden;
}

async function saveFlashcardReview(correct) {
  if (!state.selectedLesson || state.currentCardReviewed) return;
  const item = state.selectedLesson.items[state.currentCard];
  const buttons = [...document.querySelectorAll("[data-card-review]")];
  buttons.forEach((button) => { button.disabled = true; });
  try {
    await api("/progress/reviews", {
      method: "POST",
      body: JSON.stringify({ item_id: item.id, correct }),
    });
    state.currentCardReviewed = true;
    byId("card-review-message").textContent = "Practice saved to your learning history.";
    await refreshLearningData();
  } catch (error) {
    buttons.forEach((button) => { button.disabled = false; });
    showToast(error.message);
  }
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
    stopQuizTimer();
    const lessonFilter = state.quizLessonId ? `&lesson_id=${encodeURIComponent(state.quizLessonId)}` : "";
    const quiz = await api(`/quiz?language=${encodeURIComponent(state.language)}&category=${encodeURIComponent(state.quizCategory)}&level=${encodeURIComponent(state.quizLevel)}${lessonFilter}&limit=10`);
    state.quizSessionId = quiz.session_id;
    state.quizDeadline = performance.now() + (quiz.remaining_seconds ?? quiz.duration_seconds) * 1000;
    state.quizItems = quiz.questions;
    state.quizIndex = 0;
    state.quizCorrect = 0;
    state.quizAnswers = [];
    state.savedQuizResult = null;
    state.quizTimedOut = false;
    state.quizLocked = false;
    if (state.quizItems.length) {
      renderQuizTimer();
      state.quizTimer = window.setInterval(renderQuizTimer, 1000);
    }
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
    stopQuizTimer();
    root.innerHTML = `<div class="quiz-empty-state"><span>✳</span><h2>No questions in this set yet</h2><p>Choose another category, or ask an administrator to add lesson cards and quiz questions.</p></div>`;
    return;
  }
  if (state.quizIndex >= state.quizItems.length) {
    stopQuizTimer();
    const total = state.quizItems.length;
    const percent = state.savedQuizResult?.score ?? Math.round((state.quizCorrect / total) * 100);
    const correctCount = state.savedQuizResult?.correct_count ?? state.quizCorrect;
    const grade = gradeForPercent(percent);
    const missed = state.quizAnswers.filter((answer) => !answer.correct);
    const review = missed.length
      ? `<section class="quiz-review"><h3>Answers to review</h3>${missed.map((answer) => `<div class="quiz-review-row"><strong>${escapeHtml(answer.term)}</strong><span>Your answer: ${escapeHtml(answer.selected)}</span><b>Correct: ${escapeHtml(answer.translation)}</b><small>${escapeHtml(answer.explanation || "Review this lesson and try again.")}</small></div>`).join("")}</section>`
      : `<p class="quiz-perfect-note">Perfect score — you got every answer right! ✨</p>`;
    const savedNote = state.quizTimedOut
      ? `<p class="quiz-saved-note quiz-timeout-note">Time is up. Unanswered questions were marked incorrect; your result was saved.</p>`
      : state.savedQuizResult
      ? `<p class="quiz-saved-note">✓ Result saved to your account and weekly progress.</p>`
      : `<p class="quiz-saved-note">Your result is being saved. Keep this page open for a moment.</p>`;
    root.innerHTML = `<div class="quiz-results"><p class="eyebrow">${state.quizTimedOut ? "TIME IS UP" : "QUIZ COMPLETE"}</p><h2 class="quiz-question">Your result</h2><div class="quiz-grade-card"><div class="quiz-grade-letter">${grade.letter}</div><div class="quiz-grade-detail"><span>FINAL MARK</span><strong>${percent}%</strong><small>${correctCount} correct out of ${total}</small></div><div class="quiz-score-ring" style="--score:${percent}%"><span>${percent}<small>%</small></span></div></div><p class="quiz-grade-message">${grade.label}</p>${savedNote}<div class="quiz-score-stats"><div><strong>${correctCount}</strong><span>Correct answers</span></div><div><strong>${total - correctCount}</strong><span>To review</span></div><div><strong>${total}</strong><span>Questions</span></div></div>${review}<button class="button button-primary" id="quiz-restart">Try another quiz</button></div>`;
    return;
  }
  const item = state.quizItems[state.quizIndex];
  const options = item.choices || [];
  const answered = state.quizAnswers.length;
  const runningPercent = answered ? Math.round((state.quizCorrect / answered) * 100) : 0;
  const runningGrade = answered ? gradeForPercent(runningPercent).letter : "—";
  const progress = Math.round((state.quizIndex / state.quizItems.length) * 100);
  const typeLabels = { meaning: "Word meaning", recall: "Active recall", sentence: "Sentence practice", custom: "Challenge question" };
  const questionType = typeLabels[item.question_type] || "Practice question";
  root.innerHTML = `<div class="quiz-progress-header"><p class="quiz-progress">QUESTION ${state.quizIndex + 1} <span>OF ${state.quizItems.length}</span></p><span class="quiz-timer" id="quiz-timer" role="timer" aria-live="off">--:--</span><span class="quiz-running-mark">Mark so far: ${answered ? `${runningPercent}% (${runningGrade})` : "—"}</span></div><div class="quiz-progress-track"><span style="width:${progress}%"></span></div><p class="quiz-question-type">${escapeHtml(questionType)} · ${escapeHtml(item.lesson_title)} · ${escapeHtml(item.category)} · ${escapeHtml(item.level)}</p><h2 class="quiz-question">${escapeHtml(item.prompt)}</h2><p class="quiz-prompt">Choose the best answer</p><div class="quiz-options">${options.map((option) => `<button class="quiz-option" data-answer="${encodeURIComponent(option)}">${escapeHtml(option)}</button>`).join("")}</div><div class="quiz-feedback" id="quiz-feedback" aria-live="polite"></div><button class="button button-primary quiz-next" id="quiz-next" hidden>${state.quizIndex + 1 === state.quizItems.length ? "See your mark" : "Next question →"}</button>`;
  renderQuizTimer();
}
async function refreshLearningData() {
  [state.lessons, state.progress] = await Promise.all([
    api(`/lessons?language=${encodeURIComponent(state.language)}`),
    api(`/progress?language=${encodeURIComponent(state.language)}&week_start=${encodeURIComponent(state.weekStart || currentWeekStart())}`),
  ]);
  renderLessons();
  renderProgress();
  renderQuizCategories();
  renderCourseProgressDetail();
}

async function shiftWeek(direction) {
  const selectedMonday = new Date(`${state.weekStart || currentWeekStart()}T12:00:00`);
  selectedMonday.setDate(selectedMonday.getDate() + direction * 7);
  const nextWeekStart = localDateKey(selectedMonday);
  if (nextWeekStart > currentWeekStart()) return;
  state.weekStart = nextWeekStart;
  try {
    const progress = await api(`/progress?language=${encodeURIComponent(state.language)}&week_start=${encodeURIComponent(state.weekStart)}`);
    state.progress = progress;
    renderProgress();
  } catch (error) {
    showToast(error.message);
  }
}

async function selectLanguage(code) {
  const language = state.languages.find((item) => item.code === code);
  if (!language || code === state.language) return;
  state.language = code;
  localStorage.setItem("motiva-language", code);
  state.categoryFilter = "All";
  state.levelFilter = "All";
  state.quizCategory = "All";
  state.quizLevel = "All";
  byId("quiz-level").value = "All";
  state.quizLessonId = null;
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
  document.querySelectorAll(".quiz-option").forEach((option) => {
    option.disabled = true;
  });
  let result;
  try {
    result = await api("/quiz/answer", {
      method: "POST",
      body: JSON.stringify({ session_id: state.quizSessionId, question_id: item.id, answer: selected }),
    });
  } catch (error) {
    state.quizLocked = false;
    document.querySelectorAll(".quiz-option").forEach((option) => { option.disabled = false; });
    showToast(error.message);
    return;
  }

  if (result.correct) state.quizCorrect += 1;
  if (result.session_result) {
    state.savedQuizResult = result.session_result;
    stopQuizTimer();
  }
  if (result.timed_out) {
    stopQuizTimer();
    state.quizTimedOut = true;
    state.quizCorrect = result.session_result?.correct_count || 0;
    state.quizIndex = state.quizItems.length;
    renderQuizQuestion();
    try { await refreshLearningData(); } catch (error) { showToast(error.message); }
    return;
  }
  state.quizAnswers.push({
    term: item.prompt,
    translation: result.correct_answer,
    selected,
    correct: result.correct,
    explanation: result.explanation,
  });
  document.querySelectorAll(".quiz-option").forEach((option) => {
    const answer = decodeURIComponent(option.dataset.answer);
    if (answer === result.correct_answer) option.classList.add("correct");
    else if (option === button) option.classList.add("wrong");
  });
  const answered = state.quizAnswers.length;
  const mark = Math.round((state.quizCorrect / answered) * 100);
  const grade = gradeForPercent(mark).letter;
  byId("quiz-feedback").textContent = `${result.correct ? "Correct!" : `Not quite. The correct answer is “${result.correct_answer}”.`} ${result.explanation} Mark so far: ${mark}% (${grade}).`;
  byId("quiz-next").hidden = false;
  try {
    await refreshLearningData();
  } catch (error) {
    showToast(`Your answer was saved, but progress could not refresh: ${error.message}`);
  }
}

function bindEvents() {
  document.querySelectorAll(".theme-toggle").forEach((button) => button.addEventListener("click", toggleTheme));
  bindAdminEvents();
  document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.go)));
  byId("menu-toggle").addEventListener("click", () => byId("sidebar").classList.toggle("open"));
  byId("week-previous").addEventListener("click", () => shiftWeek(-1));
  byId("week-next").addEventListener("click", () => shiftWeek(1));
  byId("language-select").addEventListener("change", (event) => {
    const selected = state.languages.find((item) => item.code === event.target.value);
    if (selected) byId("course-flag").textContent = selected.flag;
    selectLanguage(event.target.value);
  });
  byId("quiz-level").addEventListener("change", (event) => {
    state.quizLessonId = null;
    state.quizLevel = event.target.value;
    startQuiz();
  });
  byId("profile-edit").addEventListener("click", openProfileDialog);
  byId("choose-profile-photo").addEventListener("click", () => byId("profile-photo-file").click());
  byId("profile-photo-file").addEventListener("change", (event) => {
    const file = event.currentTarget.files?.[0];
    if (file) readProfilePhoto(file);
  });
  byId("profile-form").addEventListener("submit", saveProfilePhoto);
  byId("remove-profile-photo").addEventListener("click", removeProfilePhoto);
  byId("profile-dialog-close").addEventListener("click", () => byId("profile-dialog").close());
  byId("profile-dialog").addEventListener("click", (event) => {
    if (event.target === byId("profile-dialog")) byId("profile-dialog").close();
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
  document.querySelectorAll("[data-card-review]").forEach((button) => {
    button.addEventListener("click", () => saveFlashcardReview(button.dataset.cardReview === "1"));
  });
  document.addEventListener("click", (event) => {
    const adminLearner = event.target.closest("[data-admin-learner]");
    if (adminLearner) renderAdminLearnerDetail(adminLearner.dataset.adminLearner);
    const adminLesson = event.target.closest("[data-admin-lesson]");
    if (adminLesson) selectAdminLesson(adminLesson.dataset.adminLesson);
    const adminAction = event.target.closest("[data-admin-action]");
    if (adminAction) handleAdminAction(adminAction.dataset.adminAction, adminAction.dataset.id);
    const card = event.target.closest("[data-lesson]");
    if (card) openLesson(card.dataset.lesson);
    const filter = event.target.closest("[data-filter]");
    if (filter) { state.categoryFilter = filter.dataset.filter; renderLessons(); }
    const levelFilter = event.target.closest("[data-level-filter]");
    if (levelFilter) { state.levelFilter = levelFilter.dataset.levelFilter; renderLessons(); }
    const category = event.target.closest("[data-quiz-category]");
    if (category) { state.quizLessonId = null; state.quizCategory = category.dataset.quizCategory; renderQuizCategories(); startQuiz(); }
    const practiceLesson = event.target.closest("#practice-current-lesson");
    if (practiceLesson) {
      state.quizLessonId = state.selectedLesson?.id || null;
      state.quizCategory = "All";
      state.quizLevel = "All";
      byId("quiz-level").value = "All";
      renderQuizCategories();
      setView("practice");
      startQuiz();
    }
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
  setTheme(document.documentElement.dataset.theme || "light", false);
  formatToday();
  state.weekStart = currentWeekStart();
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
