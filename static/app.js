const elements = {
  authView: document.querySelector("#auth-view"),
  appView: document.querySelector("#app-view"),
  showLogin: document.querySelector("#show-login"),
  showRegister: document.querySelector("#show-register"),
  loginForm: document.querySelector("#login-form"),
  registerForm: document.querySelector("#register-form"),
  loginEmail: document.querySelector("#login-email"),
  loginPassword: document.querySelector("#login-password"),
  registerName: document.querySelector("#register-name"),
  registerEmail: document.querySelector("#register-email"),
  registerPassword: document.querySelector("#register-password"),
  authMessage: document.querySelector("#auth-message"),
  welcomeText: document.querySelector("#welcome-text"),
  logoutButton: document.querySelector("#logout-button"),
  openTaskPanel: document.querySelector("#open-task-panel"),
  closeTaskPanel: document.querySelector("#close-task-panel"),
  totalCount: document.querySelector("#total-count"),
  pendingCount: document.querySelector("#pending-count"),
  inProgressCount: document.querySelector("#inprogress-count"),
  completedCount: document.querySelector("#completed-count"),
  overdueCount: document.querySelector("#overdue-count"),
  todayCount: document.querySelector("#today-count"),
  progressRing: document.querySelector("#progress-ring"),
  completionPercent: document.querySelector("#completion-percent"),
  legendDone: document.querySelector("#legend-done"),
  legendProgress: document.querySelector("#legend-progress"),
  legendPending: document.querySelector("#legend-pending"),
  formTitle: document.querySelector("#form-title"),
  taskForm: document.querySelector("#task-form"),
  taskId: document.querySelector("#task-id"),
  taskTitle: document.querySelector("#task-title"),
  taskCourse: document.querySelector("#task-course"),
  taskDescription: document.querySelector("#task-description"),
  taskDueDate: document.querySelector("#task-due-date"),
  taskPriority: document.querySelector("#task-priority"),
  taskStatus: document.querySelector("#task-status"),
  statusField: document.querySelector("#status-field"),
  submitTaskButton: document.querySelector("#submit-task-button"),
  cancelEditButton: document.querySelector("#cancel-edit-button"),
  taskSearch: document.querySelector("#task-search"),
  statusFilter: document.querySelector("#status-filter"),
  priorityFilter: document.querySelector("#priority-filter"),
  quickFilters: document.querySelectorAll("[data-quick-filter]"),
  message: document.querySelector("#message"),
  courseSummary: document.querySelector("#course-summary"),
  taskCountLabel: document.querySelector("#task-count-label"),
  taskList: document.querySelector("#task-list"),
  taskTemplate: document.querySelector("#task-template"),
};

let currentUser = null;
let currentTasks = [];
let currentSummary = { total: 0, pending: 0, inProgress: 0, completed: 0, overdue: 0, dueToday: 0 };
let quickFilter = "all";

document.addEventListener("DOMContentLoaded", async () => {
  setDefaultDueDate();
  elements.showLogin.addEventListener("click", () => showAuthForm("login"));
  elements.showRegister.addEventListener("click", () => showAuthForm("register"));
  elements.loginForm.addEventListener("submit", login);
  elements.registerForm.addEventListener("submit", register);
  elements.logoutButton.addEventListener("click", logout);
  elements.openTaskPanel.addEventListener("click", () => {
    resetTaskForm();
    focusEditor();
  });
  elements.closeTaskPanel.addEventListener("click", resetTaskForm);
  elements.taskForm.addEventListener("submit", submitTask);
  elements.cancelEditButton.addEventListener("click", resetTaskForm);
  elements.taskSearch.addEventListener("input", renderCurrentTasks);
  elements.statusFilter.addEventListener("change", renderCurrentTasks);
  elements.priorityFilter.addEventListener("change", renderCurrentTasks);
  elements.quickFilters.forEach((button) => {
    button.addEventListener("click", () => {
      quickFilter = button.dataset.quickFilter;
      elements.quickFilters.forEach((item) => item.classList.toggle("active", item === button));
      renderCurrentTasks();
    });
  });
  await loadSession();
});

async function loadSession() {
  const response = await fetch("/api/session");
  const payload = await response.json();
  if (payload.authenticated) {
    currentUser = payload.user;
    showApp();
    await loadTasks();
  } else {
    showAuth();
  }
}

function showAuthForm(mode) {
  const isLogin = mode === "login";
  elements.loginForm.classList.toggle("hidden", !isLogin);
  elements.registerForm.classList.toggle("hidden", isLogin);
  elements.showLogin.classList.toggle("active", isLogin);
  elements.showRegister.classList.toggle("active", !isLogin);
  elements.authMessage.textContent = "";
}

async function login(event) {
  event.preventDefault();
  const payload = await sendJson("/api/login", "POST", {
    email: elements.loginEmail.value,
    password: elements.loginPassword.value,
  });
  if (!payload.ok) return showAuthMessage(payload.error, true);
  currentUser = payload.data.user;
  elements.loginForm.reset();
  showApp();
  await loadTasks();
}

async function register(event) {
  event.preventDefault();
  const payload = await sendJson("/api/register", "POST", {
    name: elements.registerName.value,
    email: elements.registerEmail.value,
    password: elements.registerPassword.value,
  });
  if (!payload.ok) return showAuthMessage(payload.error, true);
  currentUser = payload.data.user;
  elements.registerForm.reset();
  showApp();
  await loadTasks();
}

async function logout() {
  await fetch("/api/logout", { method: "POST" });
  currentUser = null;
  currentTasks = [];
  resetTaskForm();
  showAuth();
}

function showAuth() {
  elements.authView.classList.remove("hidden");
  elements.appView.classList.add("hidden");
}

function showApp() {
  elements.authView.classList.add("hidden");
  elements.appView.classList.remove("hidden");
  elements.welcomeText.textContent = `Welcome back, ${currentUser.name}. Here is what needs your attention.`;
}

async function loadTasks() {
  const payload = await sendJson("/api/tasks", "GET");
  if (!payload.ok) {
    showMessage(payload.error, true);
    if (payload.status === 401) showAuth();
    return;
  }
  updateState(payload.data);
}

async function submitTask(event) {
  event.preventDefault();
  const taskId = elements.taskId.value;
  const payload = await sendJson(taskId ? `/api/tasks/${taskId}` : "/api/tasks", taskId ? "PUT" : "POST", getTaskFormData());
  if (!payload.ok) return showMessage(payload.error, true);
  updateState(payload.data);
  showMessage(taskId ? "Task updated." : "Task added.");
  resetTaskForm();
}

async function toggleTask(taskId) {
  const payload = await sendJson(`/api/tasks/${taskId}/toggle`, "POST");
  if (!payload.ok) return showMessage(payload.error, true);
  updateState(payload.data);
}

async function setTaskStatus(task, status) {
  const payload = await sendJson(`/api/tasks/${task.id}`, "PUT", {
    title: task.title,
    course: task.course,
    description: task.description,
    dueDate: task.dueDate,
    priority: task.priority,
    status,
  });
  if (!payload.ok) return showMessage(payload.error, true);
  updateState(payload.data);
}

function editTask(task) {
  elements.taskId.value = task.id;
  elements.taskTitle.value = task.title;
  elements.taskCourse.value = task.course;
  elements.taskDescription.value = task.description;
  elements.taskDueDate.value = task.dueDate;
  elements.taskPriority.value = task.priority;
  elements.taskStatus.value = task.status;
  elements.formTitle.textContent = "Edit Task";
  elements.submitTaskButton.textContent = "Save Changes";
  elements.statusField.classList.remove("hidden");
  elements.cancelEditButton.classList.remove("hidden");
  focusEditor();
}

async function deleteTask(taskId) {
  if (!window.confirm("Delete this task?")) return;
  const payload = await sendJson(`/api/tasks/${taskId}`, "DELETE");
  if (!payload.ok) return showMessage(payload.error, true);
  updateState(payload.data);
  showMessage("Task deleted.");
  if (elements.taskId.value === String(taskId)) resetTaskForm();
}

function getTaskFormData() {
  return {
    title: elements.taskTitle.value.trim(),
    course: elements.taskCourse.value.trim() || "General",
    description: elements.taskDescription.value.trim(),
    dueDate: elements.taskDueDate.value,
    priority: elements.taskPriority.value,
    status: elements.taskStatus.value,
  };
}

function resetTaskForm() {
  elements.taskForm.reset();
  elements.taskId.value = "";
  elements.taskPriority.value = "medium";
  elements.taskStatus.value = "pending";
  elements.formTitle.textContent = "Add Task";
  elements.submitTaskButton.textContent = "Add Task";
  elements.statusField.classList.add("hidden");
  elements.cancelEditButton.classList.add("hidden");
  setDefaultDueDate();
}

function focusEditor() {
  document.querySelector(".editor-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  elements.taskTitle.focus();
}

function updateState(payload) {
  currentTasks = payload.tasks;
  currentSummary = payload.summary;
  renderCurrentTasks();
}

function renderCurrentTasks() {
  const tasks = getFilteredTasks();
  elements.totalCount.textContent = currentSummary.total;
  elements.pendingCount.textContent = currentSummary.pending;
  elements.inProgressCount.textContent = currentSummary.inProgress;
  elements.completedCount.textContent = currentSummary.completed;
  elements.overdueCount.textContent = currentSummary.overdue;
  elements.todayCount.textContent = currentSummary.dueToday;
  elements.taskCountLabel.textContent = `${tasks.length} of ${currentTasks.length} tasks shown`;
  renderProgressChart();
  renderCourseSummary();

  if (!tasks.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = currentTasks.length ? "No tasks match your filters." : "No tasks yet. Add your first task.";
    elements.taskList.replaceChildren(empty);
    return;
  }

  elements.taskList.replaceChildren(...tasks.map(createTaskCard));
}

function createTaskCard(task) {
  const fragment = elements.taskTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".task-card");
  const statusLine = fragment.querySelector(".task-status-line");
  const title = fragment.querySelector(".task-title");
  const description = fragment.querySelector(".task-description");
  const course = fragment.querySelector(".course-badge");
  const due = fragment.querySelector(".due-badge");
  const priority = fragment.querySelector(".priority-badge");
  const status = fragment.querySelector(".status-badge");
  const toggle = fragment.querySelector(".toggle-button");
  const edit = fragment.querySelector(".edit-button");
  const remove = fragment.querySelector(".delete-button");

  title.textContent = task.title;
  description.textContent = task.description || "No description added.";
  course.textContent = task.course;
  due.textContent = `Due ${formatDate(task.dueDate)} ${getDueLabel(task.dueDate, task.status)}`.trim();
  priority.textContent = task.priority;
  priority.classList.add(task.priority);
  status.textContent = getStatusLabel(task.status);
  status.classList.add(task.status);
  statusLine.classList.add(task.priority);
  card.classList.toggle("done", task.status === "done");
  card.classList.toggle("overdue", isOverdue(task));
  toggle.textContent = getPrimaryActionLabel(task.status);
  toggle.addEventListener("click", () => {
    if (task.status === "pending") {
      setTaskStatus(task, "inprogress");
      return;
    }
    toggleTask(task.id);
  });
  edit.addEventListener("click", () => editTask(task));
  remove.addEventListener("click", () => deleteTask(task.id));
  return card;
}

function renderCourseSummary() {
  const courses = currentTasks.reduce((acc, task) => {
    if (!acc[task.course]) acc[task.course] = { total: 0, done: 0, inProgress: 0 };
    acc[task.course].total += 1;
    if (task.status === "done") acc[task.course].done += 1;
    if (task.status === "inprogress") acc[task.course].inProgress += 1;
    return acc;
  }, {});

  const nodes = Object.entries(courses)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([course, data]) => {
      const percent = data.total ? Math.round((data.done / data.total) * 100) : 0;
      const item = document.createElement("article");
      item.className = "course-card";
      item.innerHTML = `
        <div><strong>${escapeHtml(course)}</strong><span>${data.done}/${data.total} complete</span></div>
        <small>${data.inProgress} in progress</small>
        <div class="progress"><span style="width: ${percent}%"></span></div>
      `;
      return item;
    });
  elements.courseSummary.replaceChildren(...nodes);
}

function getFilteredTasks() {
  const query = elements.taskSearch.value.trim().toLowerCase();
  const status = elements.statusFilter.value;
  const priority = elements.priorityFilter.value;

  return currentTasks
    .filter((task) => {
      const searchable = `${task.title} ${task.course} ${task.description}`.toLowerCase();
      const matchesQuick =
        quickFilter === "all" ||
        (quickFilter === "today" && daysUntil(task.dueDate) === 0 && task.status !== "done") ||
        (quickFilter === "overdue" && isOverdue(task)) ||
        (quickFilter === "inprogress" && task.status === "inprogress");
      return (
        searchable.includes(query) &&
        (status === "all" || task.status === status) &&
        (priority === "all" || task.priority === priority) &&
        matchesQuick
      );
    })
    .sort(compareTasks);
}

function compareTasks(a, b) {
  const statusOrder = { pending: 0, inprogress: 1, done: 2 };
  if (a.status !== b.status) return statusOrder[a.status] - statusOrder[b.status];
  const dateDiff = new Date(`${a.dueDate}T00:00:00`) - new Date(`${b.dueDate}T00:00:00`);
  if (dateDiff !== 0) return dateDiff;
  const priorityOrder = { high: 0, medium: 1, low: 2 };
  return priorityOrder[a.priority] - priorityOrder[b.priority];
}

async function sendJson(url, method, body) {
  try {
    const options = { method, headers: {} };
    if (body) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    const data = await response.json();
    return { ok: response.ok, status: response.status, data, error: data.error || "Request failed." };
  } catch (error) {
    return { ok: false, status: 0, data: null, error: error.message };
  }
}

function setDefaultDueDate() {
  const today = new Date();
  elements.taskDueDate.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${value}T00:00:00`));
}

function daysUntil(value) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${value}T00:00:00`) - today) / 86400000);
}

function getDueLabel(value, status) {
  if (status === "done") return "";
  const days = daysUntil(value);
  if (days < 0) return "(overdue)";
  if (days === 0) return "(today)";
  if (days === 1) return "(tomorrow)";
  return "";
}

function isOverdue(task) {
  return task.status !== "done" && daysUntil(task.dueDate) < 0;
}

function renderProgressChart() {
  const total = currentSummary.total || 0;
  const completed = currentSummary.completed || 0;
  const inProgress = currentSummary.inProgress || 0;
  const pending = currentSummary.pending || 0;
  const completedPercent = total ? Math.round((completed / total) * 100) : 0;
  const progressPercent = total ? Math.round((inProgress / total) * 100) : 0;
  const completedDegrees = total ? (completed / total) * 360 : 0;
  const progressDegrees = total ? ((completed + inProgress) / total) * 360 : 0;

  elements.completionPercent.textContent = `${completedPercent}%`;
  elements.legendDone.textContent = completed;
  elements.legendProgress.textContent = inProgress;
  elements.legendPending.textContent = pending;
  elements.progressRing.style.background = `conic-gradient(var(--green) 0deg ${completedDegrees}deg, var(--violet) ${completedDegrees}deg ${progressDegrees}deg, #e9edf5 ${progressDegrees}deg 360deg)`;
  elements.progressRing.setAttribute("aria-label", `${completedPercent}% complete, ${progressPercent}% in progress`);
}

function getStatusLabel(status) {
  if (status === "done") return "Completed";
  if (status === "inprogress") return "In Progress";
  return "Pending";
}

function getPrimaryActionLabel(status) {
  if (status === "pending") return "Start";
  if (status === "inprogress") return "Done";
  return "Reopen";
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}

function showMessage(text, isError = false) {
  elements.message.textContent = text;
  elements.message.classList.toggle("error", isError);
  window.setTimeout(() => {
    if (elements.message.textContent === text) {
      elements.message.textContent = "";
      elements.message.classList.remove("error");
    }
  }, 3000);
}

function showAuthMessage(text, isError = false) {
  elements.authMessage.textContent = text;
  elements.authMessage.classList.toggle("error", isError);
}
