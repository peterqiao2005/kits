const STORAGE_KEY = "completion-repeat-todos";
const SETTINGS_KEY = "completion-repeat-settings";
const SENT_BROWSER_KEY = "completion-repeat-browser-sent";
const MS_PER_DAY = 24 * 60 * 60 * 1000;

const sampleTasks = [
  "美国Talkatone",
  "爱沙尼亚Esimplus",
  "香港Club Sim",
  "德国O2",
  "荷兰沃达丰",
  "德国沃达丰",
  "英国giffgaff",
].map((title, index) => ({
  id: createId(),
  title,
  dueDate: index === 0 ? toDateInput(new Date()) : "",
  dueTime: index === 0 ? "08:00" : "",
  completed: false,
  completedAt: "",
  history: [],
  listName: "手机卡保号提醒",
  priority: index === 0 ? "high" : "none",
  tags: index === 0 ? ["保号"] : [],
  notes: "",
  subtasks: [],
  repeat: index === 0
    ? { mode: "afterCompletion", every: 27, unit: "day", skipWeekends: false, skipHolidays: false }
    : { mode: "none", every: 1, unit: "day", skipWeekends: false, skipHolidays: false },
}));

const state = {
  tasks: loadTasks(),
  selectedId: "",
  view: "inbox",
  mode: "list",
  focusSeconds: 25 * 60,
  focusRunning: false,
  focusTimerId: 0,
  calendarCursor: new Date(),
  repeatDraft: null,
  settings: loadSettings(),
  session: null,
  dataUserId: "global",
  loaded: false,
};

const el = {
  taskList: document.querySelector("#taskList"),
  app: document.querySelector(".app"),
  calendarView: document.querySelector("#calendarView"),
  kanbanView: document.querySelector("#kanbanView"),
  matrixView: document.querySelector("#matrixView"),
  focusView: document.querySelector("#focusView"),
  focusTimer: document.querySelector("#focusTimer"),
  accountBadge: document.querySelector("#accountBadge"),
  focusTaskName: document.querySelector("#focusTaskName"),
  startFocus: document.querySelector("#startFocus"),
  pauseFocus: document.querySelector("#pauseFocus"),
  resetFocus: document.querySelector("#resetFocus"),
  quickAdd: document.querySelector("#quickAdd"),
  quickTitle: document.querySelector("#quickTitle"),
  detailPanel: document.querySelector("#detailPanel"),
  emptyDetail: document.querySelector("#emptyDetail"),
  detailForm: document.querySelector("#detailForm"),
  detailDone: document.querySelector("#detailDone"),
  detailTitle: document.querySelector("#detailTitle"),
  dueDate: document.querySelector("#dueDate"),
  dueTime: document.querySelector("#dueTime"),
  taskListName: document.querySelector("#taskListName"),
  priority: document.querySelector("#priority"),
  tags: document.querySelector("#tags"),
  notes: document.querySelector("#notes"),
  subtaskForm: document.querySelector("#subtaskForm"),
  subtaskTitle: document.querySelector("#subtaskTitle"),
  subtaskList: document.querySelector("#subtaskList"),
  deleteTask: document.querySelector("#deleteTask"),
  repeatToggle: document.querySelector("#repeatToggle"),
  repeatEditor: document.querySelector("#repeatEditor"),
  repeatSummary: document.querySelector("#repeatSummary"),
  repeatMode: document.querySelector("#repeatMode"),
  repeatEvery: document.querySelector("#repeatEvery"),
  repeatUnit: document.querySelector("#repeatUnit"),
  skipHolidays: document.querySelector("#skipHolidays"),
  skipWeekends: document.querySelector("#skipWeekends"),
  applyRepeat: document.querySelector("#applyRepeat"),
  cancelRepeat: document.querySelector("#cancelRepeat"),
  calendar: document.querySelector("#calendar"),
  monthLabel: document.querySelector("#monthLabel"),
  prevMonth: document.querySelector("#prevMonth"),
  nextMonth: document.querySelector("#nextMonth"),
  historyList: document.querySelector("#historyList"),
  todayCount: document.querySelector("#todayCount"),
  weekCount: document.querySelector("#weekCount"),
  allCount: document.querySelector("#allCount"),
  clearDone: document.querySelector("#clearDone"),
  sortBtn: document.querySelector("#sortBtn"),
  syncBtn: document.querySelector("#syncBtn"),
  toggleSidebar: document.querySelector("#toggleSidebar"),
  notificationBtn: document.querySelector("#notificationBtn"),
  moreMenu: document.querySelector("#moreMenu"),
  openSettings: document.querySelector("#openSettings"),
  exportData: document.querySelector("#exportData"),
  importData: document.querySelector("#importData"),
  resetSamples: document.querySelector("#resetSamples"),
  logoutBtn: document.querySelector("#logoutBtn"),
  settingsDialog: document.querySelector("#settingsDialog"),
  notificationSettings: document.querySelector("#notificationSettings"),
  closeSettings: document.querySelector("#closeSettings"),
  browserEnabled: document.querySelector("#browserEnabled"),
  serverEnabled: document.querySelector("#serverEnabled"),
  wecomWebhook: document.querySelector("#wecomWebhook"),
  feishuWebhook: document.querySelector("#feishuWebhook"),
  feishuSecret: document.querySelector("#feishuSecret"),
  genericWebhook: document.querySelector("#genericWebhook"),
  smtpHost: document.querySelector("#smtpHost"),
  smtpPort: document.querySelector("#smtpPort"),
  smtpUser: document.querySelector("#smtpUser"),
  smtpPassword: document.querySelector("#smtpPassword"),
  mailFrom: document.querySelector("#mailFrom"),
  mailTo: document.querySelector("#mailTo"),
  settingsStatus: document.querySelector("#settingsStatus"),
  testNotification: document.querySelector("#testNotification"),
};

function defaultSettings() {
  return {
    browserEnabled: false,
    serverEnabled: false,
    wecomWebhook: "",
    feishuWebhook: "",
    feishuSecret: "",
    genericWebhook: "",
    smtpHost: "",
    smtpPort: "",
    smtpUser: "",
    smtpPassword: "",
    mailFrom: "",
    mailTo: "",
  };
}

function loadTasks() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return sampleTasks.map(normalizeTask);
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeTask) : sampleTasks.map(normalizeTask);
  } catch {
    return sampleTasks.map(normalizeTask);
  }
}

function normalizeTask(task) {
  return {
    listName: "手机卡保号提醒",
    priority: "none",
    tags: [],
    notes: "",
    subtasks: [],
    repeat: { mode: "none", every: 1, unit: "day", skipWeekends: false, skipHolidays: false },
    history: [],
    ...task,
  };
}

function loadSettings() {
  const raw = localStorage.getItem(SETTINGS_KEY);
  if (!raw) return defaultSettings();
  try {
    return { ...defaultSettings(), ...JSON.parse(raw) };
  } catch {
    return defaultSettings();
  }
}

function saveSettings() {
  if (!isPortalSession()) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
  }
  syncToServer();
}

function saveTasks() {
  if (!isPortalSession()) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.tasks));
  }
  syncToServer();
}

function isPortalSession() {
  return Boolean(state.session && state.dataUserId && state.dataUserId !== "global");
}

function scopedStorageKey(baseKey) {
  if (typeof state !== "undefined" && state.dataUserId && state.dataUserId !== "global") {
    return `${baseKey}:${state.dataUserId}`;
  }
  return baseKey;
}

function toDateInput(date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function createId() {
  return `task-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}

function parseDate(value) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function addInterval(date, every, unit) {
  const next = new Date(date);
  if (unit === "day") next.setDate(next.getDate() + every);
  if (unit === "week") next.setDate(next.getDate() + every * 7);
  if (unit === "month") next.setMonth(next.getMonth() + every);
  if (unit === "year") next.setFullYear(next.getFullYear() + every);
  return next;
}

function isWeekend(date) {
  return date.getDay() === 0 || date.getDay() === 6;
}

function getNextDueDate(task) {
  const repeat = task.repeat;
  const base = repeat.mode === "afterCompletion" || !task.dueDate
    ? new Date()
    : parseDate(task.dueDate);
  let next = addInterval(base, Number(repeat.every) || 1, repeat.unit);

  while (repeat.skipWeekends && isWeekend(next)) {
    next = addInterval(next, 1, "day");
  }

  return toDateInput(next);
}

function getVisibleTasks() {
  const today = parseDate(toDateInput(new Date()));
  const weekEnd = addInterval(today, 7, "day");
  return state.tasks.filter((task) => {
    if (state.view === "done") return task.completed;
    if (task.completed) return false;
    if (state.view === "today") return task.dueDate && parseDate(task.dueDate) <= today;
    if (state.view === "week") return task.dueDate && parseDate(task.dueDate) <= weekEnd;
    return true;
  });
}

function formatDate(value) {
  if (!value) return "无日期";
  const date = parseDate(value);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

function repeatText(repeat) {
  if (!repeat || repeat.mode === "none") return "无";
  const mode = repeat.mode === "afterCompletion" ? "完成重复" : "固定重复";
  const unitMap = { day: "天", week: "周", month: "月", year: "年" };
  return `${mode} · 每 ${repeat.every} ${unitMap[repeat.unit]}`;
}

function render() {
  if (!state.loaded) {
    el.taskList.innerHTML = '<div class="empty-list">加载中...</div>';
    return;
  }
  state.tasks = state.tasks.map(normalizeTask);
  renderCounts();
  renderMode();
  renderTasks();
  renderCalendarView();
  renderKanbanView();
  renderMatrixView();
  renderFocusView();
  renderDetail();
  renderSettings();
  renderAccount();
}

function renderAccount() {
  if (!state.session) {
    el.accountBadge.textContent = "本地模式";
    el.logoutBtn.disabled = true;
    return;
  }
  el.accountBadge.textContent = state.session.email || `portal:${state.session.sub}`;
  el.logoutBtn.disabled = false;
}

function renderMode() {
  const views = {
    list: el.taskList,
    calendar: el.calendarView,
    kanban: el.kanbanView,
    matrix: el.matrixView,
    focus: el.focusView,
  };
  Object.entries(views).forEach(([mode, node]) => node.classList.toggle("hidden", state.mode !== mode));
  document.querySelectorAll(".rail-btn[data-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === state.mode);
  });
}

function renderCounts() {
  const active = state.tasks.filter((task) => !task.completed);
  const today = parseDate(toDateInput(new Date()));
  const weekEnd = addInterval(today, 7, "day");
  el.allCount.textContent = active.length;
  el.todayCount.textContent = active.filter((task) => task.dueDate && parseDate(task.dueDate) <= today).length;
  el.weekCount.textContent = active.filter((task) => task.dueDate && parseDate(task.dueDate) <= weekEnd).length;
}

function renderTasks() {
  const tasks = getVisibleTasks();
  el.taskList.innerHTML = "";
  if (!tasks.length) {
    el.taskList.innerHTML = '<div class="empty-list">没有任务</div>';
    return;
  }

  for (const task of tasks) {
    const row = document.createElement("article");
    row.className = `task-row${task.id === state.selectedId ? " selected" : ""}`;
    row.dataset.id = task.id;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = task.completed;
    checkbox.addEventListener("click", (event) => {
      event.stopPropagation();
      completeTask(task.id);
    });

    const title = document.createElement("div");
    title.className = "task-title";
    title.textContent = task.title;

    const meta = document.createElement("div");
    meta.className = "task-meta";
    if (task.repeat.mode !== "none") {
      const repeat = document.createElement("span");
      repeat.className = "repeat-chip";
      repeat.textContent = repeatText(task.repeat);
      meta.append(repeat);
    }
    if (task.priority !== "none") {
      const priority = document.createElement("span");
      priority.className = `priority-dot ${task.priority}`;
      priority.title = `优先级：${task.priority}`;
      meta.append(priority);
    }
    for (const tagText of task.tags.slice(0, 2)) {
      const tag = document.createElement("span");
      tag.className = "tag-chip";
      tag.textContent = `#${tagText}`;
      meta.append(tag);
    }
    const date = document.createElement("span");
    date.textContent = task.completed ? "已完成" : formatDate(task.dueDate);
    if (task.dueDate && parseDate(task.dueDate) < parseDate(toDateInput(new Date()))) date.className = "overdue";
    meta.append(date);

    row.append(checkbox, title, meta);
    row.addEventListener("click", () => selectTask(task.id));
    el.taskList.append(row);
  }
}

function renderCalendarView() {
  el.calendarView.innerHTML = "";
  const today = parseDate(toDateInput(new Date()));
  const start = addInterval(today, -today.getDay(), "day");
  for (let index = 0; index < 14; index += 1) {
    const date = addInterval(start, index, "day");
    const value = toDateInput(date);
    const cell = document.createElement("section");
    cell.className = "calendar-cell";
    cell.innerHTML = `<header>${date.getMonth() + 1}/${date.getDate()}</header>`;
    state.tasks
      .filter((task) => !task.completed && task.dueDate === value)
      .forEach((task) => cell.append(taskCardButton(task, "calendar-task")));
    el.calendarView.append(cell);
  }
}

function renderKanbanView() {
  const groups = [
    ["overdue", "已逾期", (task) => task.dueDate && parseDate(task.dueDate) < parseDate(toDateInput(new Date()))],
    ["today", "今天", (task) => task.dueDate === toDateInput(new Date())],
    ["upcoming", "后续", (task) => task.dueDate && parseDate(task.dueDate) > parseDate(toDateInput(new Date()))],
    ["none", "无日期", (task) => !task.dueDate],
  ];
  renderGroupedBoard(el.kanbanView, groups);
}

function renderMatrixView() {
  const today = parseDate(toDateInput(new Date()));
  const groups = [
    ["do", "重要且紧急", (task) => task.priority === "high" && task.dueDate && parseDate(task.dueDate) <= today],
    ["plan", "重要不紧急", (task) => task.priority === "high" && (!task.dueDate || parseDate(task.dueDate) > today)],
    ["delegate", "紧急不重要", (task) => task.priority !== "high" && task.dueDate && parseDate(task.dueDate) <= today],
    ["later", "不重要不紧急", (task) => task.priority !== "high" && (!task.dueDate || parseDate(task.dueDate) > today)],
  ];
  renderGroupedBoard(el.matrixView, groups, "matrix-cell");
}

function renderGroupedBoard(container, groups, className = "board-col") {
  container.innerHTML = "";
  const active = state.tasks.filter((task) => !task.completed);
  for (const [, title, predicate] of groups) {
    const column = document.createElement("section");
    column.className = className;
    column.innerHTML = `<h2>${title}</h2>`;
    active.filter(predicate).forEach((task) => column.append(taskCardButton(task, "board-card")));
    container.append(column);
  }
}

function taskCardButton(task, className) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.innerHTML = `<strong></strong><span>${formatDate(task.dueDate)}${task.dueTime ? ` ${task.dueTime}` : ""}</span>`;
  button.querySelector("strong").textContent = task.title;
  button.addEventListener("click", () => selectTask(task.id));
  return button;
}

function renderFocusView() {
  const minutes = Math.floor(state.focusSeconds / 60).toString().padStart(2, "0");
  const seconds = (state.focusSeconds % 60).toString().padStart(2, "0");
  el.focusTimer.textContent = `${minutes}:${seconds}`;
  el.focusTaskName.textContent = currentTask()?.title || "选择任务后开始专注";
}

function renderDetail() {
  const task = currentTask();
  el.emptyDetail.classList.toggle("hidden", Boolean(task));
  el.detailForm.classList.toggle("hidden", !task);
  el.detailPanel.classList.toggle("open", Boolean(task));
  if (!task) return;

  el.detailDone.checked = task.completed;
  el.detailTitle.value = task.title;
  el.dueDate.value = task.dueDate;
  el.dueTime.value = task.dueTime;
  el.taskListName.value = task.listName;
  el.priority.value = task.priority;
  el.tags.value = task.tags.join(", ");
  el.notes.value = task.notes;
  setRepeatInputs(task.repeat);
  el.repeatSummary.textContent = repeatText(task.repeat);
  state.calendarCursor = task.dueDate ? parseDate(task.dueDate) : state.calendarCursor;
  renderCalendar();
  renderHistory(task);
  renderSubtasks(task);
}

function renderSubtasks(task) {
  el.subtaskList.innerHTML = "";
  if (!task.subtasks.length) {
    el.subtaskList.innerHTML = '<li><span></span><span>暂无子任务</span><span></span></li>';
    return;
  }
  task.subtasks.forEach((subtask) => {
    const li = document.createElement("li");
    li.className = subtask.done ? "done" : "";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = subtask.done;
    checkbox.addEventListener("change", () => {
      subtask.done = checkbox.checked;
      saveTasks();
      render();
    });
    const title = document.createElement("span");
    title.textContent = subtask.title;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.title = "删除子任务";
    remove.addEventListener("click", () => {
      task.subtasks = task.subtasks.filter((item) => item.id !== subtask.id);
      saveTasks();
      render();
    });
    li.append(checkbox, title, remove);
    el.subtaskList.append(li);
  });
}

function renderHistory(task) {
  el.historyList.innerHTML = "";
  if (!task.history.length) {
    el.historyList.innerHTML = "<li>暂无记录</li>";
    return;
  }
  for (const item of task.history.slice().reverse()) {
    const li = document.createElement("li");
    li.textContent = `${item.completedAt}${item.nextDueDate ? `，下次 ${item.nextDueDate}` : ""}`;
    el.historyList.append(li);
  }
}

function renderCalendar() {
  const task = currentTask();
  const cursor = state.calendarCursor || new Date();
  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  el.monthLabel.textContent = `${year}年${month + 1}月`;
  el.calendar.innerHTML = "";

  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - first.getDay());
  const selected = task?.dueDate || "";
  const today = toDateInput(new Date());

  for (let index = 0; index < 42; index += 1) {
    const date = addInterval(start, index, "day");
    const value = toDateInput(date);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "day";
    if (date.getMonth() !== month) button.classList.add("muted");
    if (value === selected) button.classList.add("selected");
    if (value === today) button.classList.add("today");
    button.textContent = date.getDate();
    button.addEventListener("click", () => updateSelected({ dueDate: value }));
    el.calendar.append(button);
  }
}

function setRepeatInputs(repeat) {
  const source = state.repeatDraft || repeat;
  el.repeatMode.value = source.mode;
  el.repeatEvery.value = source.every;
  el.repeatUnit.value = source.unit;
  el.skipHolidays.checked = source.skipHolidays;
  el.skipWeekends.checked = source.skipWeekends;
}

function currentTask() {
  return state.tasks.find((task) => task.id === state.selectedId);
}

function selectTask(id) {
  state.selectedId = id;
  state.repeatDraft = null;
  render();
}

function updateSelected(patch) {
  const task = currentTask();
  if (!task) return;
  Object.assign(task, patch);
  saveTasks();
  render();
}

function completeTask(id) {
  const task = state.tasks.find((item) => item.id === id);
  if (!task) return;
  const completedAt = new Date().toLocaleString("zh-CN", { hour12: false });

  if (!task.completed && task.repeat.mode !== "none") {
    const nextDueDate = getNextDueDate(task);
    task.history.push({ completedAt, nextDueDate });
    task.dueDate = nextDueDate;
    task.completed = false;
  } else {
    task.completed = !task.completed;
    task.completedAt = task.completed ? completedAt : "";
    if (task.completed) task.history.push({ completedAt, nextDueDate: "" });
  }

  saveTasks();
  render();
}

function reminderDate(task) {
  if (!task.dueDate) return null;
  const date = parseDate(task.dueDate);
  if (task.dueTime) {
    const [hour, minute] = task.dueTime.split(":").map(Number);
    date.setHours(hour || 0, minute || 0, 0, 0);
  } else {
    date.setHours(9, 0, 0, 0);
  }
  return date;
}

function taskReminderKey(task) {
  return `${state.dataUserId}:${task.id}:${task.dueDate || ""}:${task.dueTime || ""}`;
}

function loadSentBrowserKeys() {
  try {
    return JSON.parse(localStorage.getItem(scopedStorageKey(SENT_BROWSER_KEY)) || "[]");
  } catch {
    return [];
  }
}

function saveSentBrowserKeys(keys) {
  localStorage.setItem(scopedStorageKey(SENT_BROWSER_KEY), JSON.stringify(keys.slice(-500)));
}

function checkBrowserReminders() {
  if (!state.settings.browserEnabled || !("Notification" in window) || Notification.permission !== "granted") return;
  const sent = new Set(loadSentBrowserKeys());
  const now = new Date();

  for (const task of state.tasks) {
    if (task.completed) continue;
    const due = reminderDate(task);
    if (!due || due > now) continue;
    const key = taskReminderKey(task);
    if (sent.has(key)) continue;
    new Notification("待办提醒", {
      body: `${task.title} ${task.dueTime || ""}`.trim(),
      tag: key,
    });
    sent.add(key);
  }

  saveSentBrowserKeys([...sent]);
}

function createTask(title) {
  const task = {
    id: createId(),
    title,
    dueDate: toDateInput(new Date()),
    dueTime: "",
    completed: false,
    completedAt: "",
    history: [],
    listName: "手机卡保号提醒",
    priority: "none",
    tags: [],
    notes: "",
    subtasks: [],
    repeat: { mode: "none", every: 1, unit: "day", skipWeekends: false, skipHolidays: false },
  };
  state.tasks.unshift(task);
  state.selectedId = task.id;
  saveTasks();
  render();
}

function deleteSelected() {
  const task = currentTask();
  if (!task) return;
  state.tasks = state.tasks.filter((item) => item.id !== task.id);
  state.selectedId = "";
  saveTasks();
  render();
}

function bindEvents() {
  el.quickAdd.addEventListener("submit", (event) => {
    event.preventDefault();
    const title = el.quickTitle.value.trim();
    if (!title) return;
    createTask(title);
    el.quickTitle.value = "";
  });

  document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      document.querySelectorAll(".nav-item[data-view]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      render();
    });
  });

  el.detailDone.addEventListener("change", () => completeTask(state.selectedId));
  el.detailTitle.addEventListener("input", () => updateSelected({ title: el.detailTitle.value }));
  el.dueDate.addEventListener("change", () => updateSelected({ dueDate: el.dueDate.value }));
  el.dueTime.addEventListener("change", () => updateSelected({ dueTime: el.dueTime.value }));
  el.taskListName.addEventListener("input", () => updateSelected({ listName: el.taskListName.value.trim() || "收集箱" }));
  el.priority.addEventListener("change", () => updateSelected({ priority: el.priority.value }));
  el.tags.addEventListener("change", () => {
    const tags = el.tags.value
      .split(/[,，]/)
      .map((tag) => tag.trim())
      .filter(Boolean);
    updateSelected({ tags });
  });
  el.notes.addEventListener("input", () => updateSelected({ notes: el.notes.value }));
  el.subtaskForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const task = currentTask();
    const title = el.subtaskTitle.value.trim();
    if (!task || !title) return;
    task.subtasks.push({ id: createId(), title, done: false });
    el.subtaskTitle.value = "";
    saveTasks();
    render();
  });
  el.deleteTask.addEventListener("click", deleteSelected);

  el.repeatToggle.addEventListener("click", () => {
    el.repeatEditor.classList.toggle("hidden");
  });

  el.applyRepeat.addEventListener("click", () => {
    updateSelected({
      repeat: {
        mode: el.repeatMode.value,
        every: Math.max(1, Number(el.repeatEvery.value) || 1),
        unit: el.repeatUnit.value,
        skipWeekends: el.skipWeekends.checked,
        skipHolidays: el.skipHolidays.checked,
      },
    });
    el.repeatEditor.classList.add("hidden");
  });

  el.cancelRepeat.addEventListener("click", () => {
    state.repeatDraft = null;
    setRepeatInputs(currentTask().repeat);
    el.repeatEditor.classList.add("hidden");
  });

  el.prevMonth.addEventListener("click", () => {
    state.calendarCursor = addInterval(state.calendarCursor, -1, "month");
    renderCalendar();
  });

  el.nextMonth.addEventListener("click", () => {
    state.calendarCursor = addInterval(state.calendarCursor, 1, "month");
    renderCalendar();
  });

  el.clearDone.addEventListener("click", () => {
    state.tasks = state.tasks.filter((task) => !task.completed);
    saveTasks();
    render();
  });

  el.sortBtn.addEventListener("click", () => {
    state.tasks.sort((a, b) => (a.dueDate || "9999-12-31").localeCompare(b.dueDate || "9999-12-31"));
    saveTasks();
    render();
  });

  el.toggleSidebar.addEventListener("click", () => {
    el.app.classList.toggle("sidebar-collapsed");
  });

  el.syncBtn.addEventListener("click", async () => {
    await syncNow();
    el.syncBtn.textContent = "✓";
    window.setTimeout(() => {
      el.syncBtn.textContent = "↻";
    }, 900);
  });

  document.querySelectorAll(".rail-btn[data-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      render();
    });
  });

  el.startFocus.addEventListener("click", startFocus);
  el.pauseFocus.addEventListener("click", pauseFocus);
  el.resetFocus.addEventListener("click", resetFocus);

  el.notificationBtn.addEventListener("click", () => {
    el.moreMenu.classList.toggle("hidden");
  });

  el.exportData.addEventListener("click", () => {
    const data = JSON.stringify({ tasks: state.tasks, settings: state.settings }, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `todoist-backup-${toDateInput(new Date())}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    el.moreMenu.classList.add("hidden");
  });

  el.openSettings.addEventListener("click", () => {
    el.moreMenu.classList.add("hidden");
    renderSettings();
    el.settingsDialog.showModal();
    pingServer();
  });

  el.importData.addEventListener("change", async () => {
    const file = el.importData.files[0];
    if (!file) return;
    const data = JSON.parse(await file.text());
    if (Array.isArray(data.tasks)) state.tasks = data.tasks.map(normalizeTask);
    if (data.settings) state.settings = { ...defaultSettings(), ...data.settings };
    saveTasks();
    saveSettings();
    render();
    el.moreMenu.classList.add("hidden");
    el.importData.value = "";
  });

  el.resetSamples.addEventListener("click", () => {
    state.tasks = sampleTasks.map(normalizeTask);
    state.selectedId = state.tasks[0]?.id || "";
    saveTasks();
    render();
    el.moreMenu.classList.add("hidden");
  });

  el.logoutBtn.addEventListener("click", async () => {
    await postJson("/api/logout", {});
    state.session = null;
    window.location.reload();
  });

  document.addEventListener("click", (event) => {
    if (!el.moreMenu.contains(event.target) && event.target !== el.notificationBtn) {
      el.moreMenu.classList.add("hidden");
    }
  });

  el.closeSettings.addEventListener("click", () => el.settingsDialog.close());

  el.notificationSettings.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.settings = readSettingsForm();
    if (state.settings.browserEnabled && "Notification" in window && Notification.permission === "default") {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") state.settings.browserEnabled = false;
    }
    if (state.settings.browserEnabled && !("Notification" in window)) state.settings.browserEnabled = false;
    saveSettings();
    renderSettings();
    el.settingsStatus.textContent = "已保存通知设置。";
  });

  el.testNotification.addEventListener("click", async () => {
    state.settings = readSettingsForm();
    saveSettings();
    if (state.settings.browserEnabled && "Notification" in window) {
      if (Notification.permission === "default") await Notification.requestPermission();
      if (Notification.permission === "granted") new Notification("待办测试提醒", { body: "浏览器提醒已启用。" });
    }
    const result = await postJson("/api/test-notification", { settings: state.settings });
    el.settingsStatus.textContent = result.ok ? "测试通知已发送。" : `后端测试失败：${result.error || "server.py 未运行"}`;
  });
}

function renderSettings() {
  el.browserEnabled.checked = Boolean(state.settings.browserEnabled);
  el.serverEnabled.checked = Boolean(state.settings.serverEnabled);
  el.wecomWebhook.value = state.settings.wecomWebhook || "";
  el.feishuWebhook.value = state.settings.feishuWebhook || "";
  el.feishuSecret.value = state.settings.feishuSecret || "";
  el.genericWebhook.value = state.settings.genericWebhook || "";
  el.smtpHost.value = state.settings.smtpHost || "";
  el.smtpPort.value = state.settings.smtpPort || "";
  el.smtpUser.value = state.settings.smtpUser || "";
  el.smtpPassword.value = state.settings.smtpPassword || "";
  el.mailFrom.value = state.settings.mailFrom || "";
  el.mailTo.value = state.settings.mailTo || "";
}

function readSettingsForm() {
  return {
    browserEnabled: el.browserEnabled.checked,
    serverEnabled: el.serverEnabled.checked,
    wecomWebhook: el.wecomWebhook.value.trim(),
    feishuWebhook: el.feishuWebhook.value.trim(),
    feishuSecret: el.feishuSecret.value.trim(),
    genericWebhook: el.genericWebhook.value.trim(),
    smtpHost: el.smtpHost.value.trim(),
    smtpPort: el.smtpPort.value.trim(),
    smtpUser: el.smtpUser.value.trim(),
    smtpPassword: el.smtpPassword.value,
    mailFrom: el.mailFrom.value.trim(),
    mailTo: el.mailTo.value.trim(),
  };
}

function startFocus() {
  if (state.focusRunning) return;
  state.focusRunning = true;
  state.focusTimerId = window.setInterval(() => {
    state.focusSeconds = Math.max(0, state.focusSeconds - 1);
    renderFocusView();
    if (state.focusSeconds === 0) {
      pauseFocus();
      if ("Notification" in window && Notification.permission === "granted") {
        new Notification("专注完成", { body: currentTask()?.title || "25 分钟专注结束。" });
      }
    }
  }, 1000);
}

function pauseFocus() {
  state.focusRunning = false;
  window.clearInterval(state.focusTimerId);
}

function resetFocus() {
  pauseFocus();
  state.focusSeconds = 25 * 60;
  renderFocusView();
}

async function postJson(url, payload) {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await response.json();
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

async function loadFromServer() {
  const result = await postJson("/api/load", {});
  if (!result.ok) return;
  if (Array.isArray(result.tasks) && result.tasks.length) {
    state.tasks = result.tasks.map(normalizeTask);
  } else if (result.session) {
    state.tasks = [];
  } else if (!localStorage.getItem(STORAGE_KEY)) {
    state.tasks = sampleTasks.map(normalizeTask);
  }
  if (result.settings) {
    state.settings = { ...defaultSettings(), ...result.settings };
  }
  state.session = result.session || null;
  state.dataUserId = result.dataUserId || (state.session ? `portal:${state.session.sub}` : "global");
}

let syncTimer = 0;
function syncToServer() {
  window.clearTimeout(syncTimer);
  syncTimer = window.setTimeout(() => {
    syncNow();
  }, 250);
}

async function syncNow() {
  return postJson("/api/sync", { tasks: state.tasks, settings: state.settings });
}

async function pingServer() {
  const result = await postJson("/api/ping", {});
  el.settingsStatus.textContent = result.ok
    ? "后端已连接；微信、飞书、邮件、webhook 可由 server.py 定时发送。"
    : "后端未连接；浏览器提醒可用，其他通道需要运行 python server.py。";
}

async function boot() {
  render();
  await loadFromServer();
  state.loaded = true;
  bindEvents();
  el.repeatEditor.classList.add("hidden");
  state.selectedId = state.tasks[0]?.id || "";
  render();
  syncToServer();
  window.setInterval(checkBrowserReminders, 30 * 1000);
  checkBrowserReminders();
}

boot();
