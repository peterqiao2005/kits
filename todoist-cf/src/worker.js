const SESSION_COOKIE = "todoist_cf_session";
const SESSION_MAX_AGE = 7 * 24 * 60 * 60;

const DEFAULT_SETTINGS = {
  browserEnabled: false,
  serverEnabled: false,
  wecomWebhook: "",
  feishuWebhook: "",
  feishuSecret: "",
  genericWebhook: "",
  resendApiKey: "",
  mailFrom: "",
  mailTo: "",
};

const SAMPLE_TASKS = [
  "美国Talkatone",
  "爱沙尼亚Esimplus",
  "香港Club Sim",
  "德国O2",
  "荷兰沃达丰",
  "德国沃达丰",
  "英国giffgaff",
].map((title, index) => ({
  id: `task-${index + 1}`,
  title,
  dueDate: index === 0 ? new Date().toISOString().slice(0, 10) : "",
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

export default {
  async fetch(request, env) {
    await ensureSchema(env);
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") return htmlResponse(APP_HTML);
    if (request.method === "GET" && url.pathname === "/app.js") return jsResponse(APP_JS);
    if (request.method === "GET" && url.pathname === "/styles.css") return cssResponse(APP_CSS);
    if (request.method === "GET" && url.pathname === "/sso/portal") return handleSso(request, env);

    if (url.pathname.startsWith("/api/")) return handleApi(request, env, url);
    return new Response("Not found", { status: 404 });
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(runReminderSweep(env));
  },
};

async function ensureSchema(env) {
  await env.DB.batch([
    env.DB.prepare("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS user_data (user_id TEXT PRIMARY KEY, tasks_json TEXT NOT NULL DEFAULT '[]', settings_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL)"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS sent_reminders (user_id TEXT NOT NULL, reminder_key TEXT NOT NULL, sent_at INTEGER NOT NULL, PRIMARY KEY (user_id, reminder_key))"),
    env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_sent_reminders_sent_at ON sent_reminders(sent_at)"),
  ]);
}

async function handleSso(request, env) {
  const url = new URL(request.url);
  const token = url.searchParams.get("token") || "";
  const { payload, error } = await verifyPortalToken(token, env.PORTAL_SSO_SECRET);
  if (error) return new Response(error, { status: 401 });

  const now = nowSeconds();
  const userId = `portal:${payload.sub}`;
  await env.DB.prepare(
    "INSERT INTO users (id, email, created_at, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET email = excluded.email, updated_at = excluded.updated_at",
  ).bind(userId, payload.email || "", now, now).run();

  const cookie = await createSessionCookie(payload, env);
  return new Response(null, {
    status: 302,
    headers: {
      "Location": "/",
      "Set-Cookie": `${SESSION_COOKIE}=${cookie}; Path=/; Max-Age=${SESSION_MAX_AGE}; HttpOnly; SameSite=Lax${secureCookieSuffix(request)}`,
    },
  });
}

async function handleApi(request, env, url) {
  if (request.method !== "POST") return json({ ok: false, error: "method not allowed" }, 405);
  const session = await readSession(request, env);

  if (url.pathname === "/api/ping") return json({ ok: true });
  if (url.pathname === "/api/session") {
    if (!session) return json({ authenticated: false });
    return json({
      authenticated: true,
      userId: session.sub,
      email: session.email || "",
      loginMethod: "portal",
      dataUserId: `portal:${session.sub}`,
    });
  }
  if (url.pathname === "/api/logout") {
    return new Response(null, {
      status: 204,
      headers: { "Set-Cookie": `${SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax${secureCookieSuffix(request)}` },
    });
  }

  if (!session) return json({ ok: false, error: "unauthorized" }, 401);
  const userId = `portal:${session.sub}`;
  const payload = await readJson(request);

  if (url.pathname === "/api/load") {
    const data = await loadUserData(env, userId);
    return json({ ok: true, dataUserId: userId, session, tasks: data.tasks, settings: data.settings });
  }

  if (url.pathname === "/api/sync") {
    const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
    const settings = normalizeSettings(payload.settings);
    await saveUserData(env, userId, tasks, settings);
    return json({ ok: true, dataUserId: userId });
  }

  if (url.pathname === "/api/test-notification") {
    const settings = normalizeSettings(payload.settings || (await loadUserData(env, userId)).settings);
    const result = await sendAll(settings, "待办测试提醒：通知通道已连接。", null, env);
    return json({ ok: result.errors.length === 0, dataUserId: userId, channels: result.channels, errors: result.errors });
  }

  return json({ ok: false, error: "not found" }, 404);
}

async function loadUserData(env, userId) {
  const row = await env.DB.prepare("SELECT tasks_json, settings_json FROM user_data WHERE user_id = ?").bind(userId).first();
  if (!row) return { tasks: [], settings: { ...DEFAULT_SETTINGS } };
  return {
    tasks: safeJson(row.tasks_json, []),
    settings: normalizeSettings(safeJson(row.settings_json, {})),
  };
}

async function saveUserData(env, userId, tasks, settings) {
  await env.DB.prepare(
    "INSERT INTO user_data (user_id, tasks_json, settings_json, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET tasks_json = excluded.tasks_json, settings_json = excluded.settings_json, updated_at = excluded.updated_at",
  ).bind(userId, JSON.stringify(tasks), JSON.stringify(normalizeSettings(settings)), nowSeconds()).run();
}

async function runReminderSweep(env) {
  await ensureSchema(env);
  const rows = await env.DB.prepare("SELECT user_id, tasks_json, settings_json FROM user_data").all();
  for (const row of rows.results || []) {
    const userId = row.user_id;
    const tasks = safeJson(row.tasks_json, []);
    const settings = normalizeSettings(safeJson(row.settings_json, {}));
    if (!settings.serverEnabled) continue;

    for (const task of tasks) {
      if (task.completed) continue;
      const dueAt = dueTimestamp(task);
      if (!dueAt || dueAt > Date.now()) continue;
      const key = `${task.id}:${task.dueDate || ""}:${task.dueTime || ""}`;
      const existing = await env.DB.prepare("SELECT reminder_key FROM sent_reminders WHERE user_id = ? AND reminder_key = ?").bind(userId, key).first();
      if (existing) continue;
      const result = await sendAll(settings, reminderText(task), task, env);
      if (result.channels.length) {
        await env.DB.prepare("INSERT OR IGNORE INTO sent_reminders (user_id, reminder_key, sent_at) VALUES (?, ?, ?)").bind(userId, key, nowSeconds()).run();
      }
    }
  }
}

function dueTimestamp(task) {
  if (!task.dueDate) return 0;
  const time = task.dueTime || "09:00";
  const parsed = Date.parse(`${task.dueDate}T${time}:00`);
  return Number.isFinite(parsed) ? parsed : 0;
}

function reminderText(task) {
  const due = [task.dueDate, task.dueTime].filter(Boolean).join(" ");
  return `待办提醒：${task.title || "未命名任务"}\n到期时间：${due || "未设置"}`;
}

async function sendAll(settings, text, task, env) {
  const channels = [];
  const errors = [];
  for (const sender of [sendWeCom, sendFeishu, sendGenericWebhook, sendResendEmail]) {
    try {
      const sent = await sender(settings, text, task, env);
      channels.push(...sent);
    } catch (error) {
      errors.push(`${sender.name}: ${error.message || String(error)}`);
    }
  }
  return { channels, errors };
}

async function sendWeCom(settings, text) {
  const raw = (settings.wecomWebhook || "").trim();
  if (!raw) return [];
  const url = raw.startsWith("http") ? raw : `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${raw}`;
  await checkedFetch(url, { msgtype: "text", text: { content: text } });
  return ["wecom"];
}

async function sendFeishu(settings, text) {
  const url = (settings.feishuWebhook || "").trim();
  if (!url) return [];
  const payload = { msg_type: "text", content: { text } };
  if ((settings.feishuSecret || "").trim()) {
    const timestamp = String(nowSeconds());
    payload.timestamp = timestamp;
    payload.sign = await feishuSign(timestamp, settings.feishuSecret);
  }
  await checkedFetch(url, payload);
  return ["feishu"];
}

async function sendGenericWebhook(settings, text, task) {
  const url = (settings.genericWebhook || "").trim();
  if (!url) return [];
  await checkedFetch(url, { text, task: task || {} });
  return ["webhook"];
}

async function sendResendEmail(settings, text, _task, env) {
  const apiKey = (settings.resendApiKey || env.RESEND_API_KEY || "").trim();
  const to = (settings.mailTo || "").trim();
  const from = (settings.mailFrom || "").trim();
  if (!apiKey || !to || !from) return [];
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ from, to, subject: "待办提醒", text }),
  });
  if (!response.ok) throw new Error(`resend ${response.status}: ${await response.text()}`);
  return ["email"];
}

async function checkedFetch(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
}

async function feishuSign(timestamp, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(`${timestamp}\n${secret}`),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new Uint8Array());
  return btoa(String.fromCharCode(...new Uint8Array(signature)));
}

async function verifyPortalToken(token, secret) {
  const parts = String(token || "").split(".");
  if (parts.length !== 3) return { error: "Invalid token format" };
  const expected = await hmacBytes(`${parts[0]}.${parts[1]}`, secret);
  const actual = base64UrlDecode(parts[2]);
  if (!timingSafeEqual(expected, actual)) return { error: "Invalid token signature" };

  let payload;
  try {
    payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(parts[1])));
  } catch {
    return { error: "Invalid token payload" };
  }
  const now = nowSeconds();
  if (payload.iss !== "portal") return { error: "Invalid issuer" };
  if (Number(payload.exp || 0) < now) return { error: "Token expired" };
  if (!String(payload.sub || "").trim()) return { error: "Missing subject" };
  return { payload };
}

async function createSessionCookie(payload, env) {
  const now = nowSeconds();
  const session = {
    sub: String(payload.sub || ""),
    email: String(payload.email || ""),
    loginMethod: "portal",
    iat: now,
    exp: now + SESSION_MAX_AGE,
    nonce: crypto.randomUUID(),
  };
  const encoded = base64UrlEncode(new TextEncoder().encode(JSON.stringify(session)));
  const sig = base64UrlEncode(await hmacBytes(encoded, env.SESSION_SECRET || env.PORTAL_SSO_SECRET));
  return `${encoded}.${sig}`;
}

async function readSession(request, env) {
  const cookie = readCookie(request.headers.get("Cookie") || "", SESSION_COOKIE);
  if (!cookie.includes(".")) return null;
  const [encoded, sig] = cookie.split(/\.(?=[^.]+$)/);
  const expected = base64UrlEncode(await hmacBytes(encoded, env.SESSION_SECRET || env.PORTAL_SSO_SECRET));
  if (!timingSafeEqual(new TextEncoder().encode(sig), new TextEncoder().encode(expected))) return null;
  try {
    const payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(encoded)));
    if (Number(payload.exp || 0) < nowSeconds()) return null;
    if (!String(payload.sub || "").trim()) return null;
    return payload;
  } catch {
    return null;
  }
}

async function hmacBytes(value, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret || ""),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value)));
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

function base64UrlEncode(bytes) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlDecode(value) {
  const normalized = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
  return Uint8Array.from(atob(padded), (char) => char.charCodeAt(0));
}

function readCookie(header, name) {
  return header
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=") || "";
}

function secureCookieSuffix(request) {
  return new URL(request.url).protocol === "https:" ? "; Secure" : "";
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

function safeJson(value, fallback) {
  try {
    return JSON.parse(value || "");
  } catch {
    return fallback;
  }
}

function normalizeSettings(settings) {
  return { ...DEFAULT_SETTINGS, ...(settings && typeof settings === "object" ? settings : {}) };
}

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function htmlResponse(body) {
  return new Response(body, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

function jsResponse(body) {
  return new Response(body, { headers: { "Content-Type": "text/javascript; charset=utf-8" } });
}

function cssResponse(body) {
  return new Response(body, { headers: { "Content-Type": "text/css; charset=utf-8" } });
}

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

const APP_HTML = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CF 待办</title>
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <div class="app">
      <aside>
        <div class="brand">Todo CF</div>
        <button data-view="inbox" class="active">收集箱 <b id="allCount">0</b></button>
        <button data-view="today">今天 <b id="todayCount">0</b></button>
        <button data-view="week">最近7天 <b id="weekCount">0</b></button>
        <button data-view="done">已完成</button>
        <button id="syncBtn">同步</button>
      </aside>
      <main>
        <header>
          <div>
            <h1>完成重复待办</h1>
            <span id="account">未登录</span>
          </div>
          <div class="actions">
            <button id="settingsBtn">通知设置</button>
            <button id="logoutBtn">退出</button>
          </div>
        </header>
        <form id="quickAdd" class="quick">
          <input id="quickTitle" placeholder="+ 添加任务" />
          <button>添加</button>
        </form>
        <section id="tasks"></section>
      </main>
      <aside class="detail" id="detail">
        <p id="emptyDetail">选择任务</p>
        <form id="detailForm" class="hidden">
          <input id="title" class="title" />
          <label>日期 <input id="dueDate" type="date" /></label>
          <label>时间 <input id="dueTime" type="time" /></label>
          <label>优先级 <select id="priority"><option value="none">无</option><option value="low">低</option><option value="medium">中</option><option value="high">高</option></select></label>
          <label>标签 <input id="tags" placeholder="逗号分隔" /></label>
          <label>备注 <textarea id="notes"></textarea></label>
          <fieldset>
            <legend>重复</legend>
            <select id="repeatMode"><option value="none">不重复</option><option value="afterCompletion">完成重复</option><option value="fixedSchedule">固定日程重复</option></select>
            <div class="row"><span>每</span><input id="repeatEvery" type="number" min="1" value="1" /><select id="repeatUnit"><option value="day">天</option><option value="week">周</option><option value="month">月</option><option value="year">年</option></select></div>
          </fieldset>
          <button type="button" id="deleteTask">删除任务</button>
        </form>
      </aside>
    </div>
    <dialog id="settingsDialog">
      <form id="settingsForm">
        <header><h2>通知设置</h2><button type="button" id="closeSettings">×</button></header>
        <label><input id="serverEnabled" type="checkbox" /> 后端提醒</label>
        <label>企业微信 Webhook/Key <input id="wecomWebhook" /></label>
        <label>飞书 Webhook <input id="feishuWebhook" /></label>
        <label>飞书 Secret <input id="feishuSecret" type="password" /></label>
        <label>通用 Webhook <input id="genericWebhook" /></label>
        <label>Resend API Key <input id="resendApiKey" type="password" /></label>
        <label>发件人 <input id="mailFrom" /></label>
        <label>收件人 <input id="mailTo" /></label>
        <div class="dialog-actions"><button type="button" id="testNotify">测试</button><button>保存</button></div>
        <p id="settingsStatus"></p>
      </form>
    </dialog>
    <script src="/app.js"></script>
  </body>
</html>`;

const APP_CSS = `
*{box-sizing:border-box}body{margin:0;font-family:Inter,"Microsoft YaHei",system-ui,sans-serif;color:#1f2328;background:#fff}.app{display:grid;grid-template-columns:240px minmax(420px,1fr)360px;min-height:100vh}aside{border-right:1px solid #e8ebef;padding:24px 14px}.brand{font-weight:800;margin-bottom:18px}aside button{display:flex;justify-content:space-between;align-items:center;width:100%;min-height:38px;border:0;border-radius:7px;background:transparent;padding:0 10px;text-align:left;cursor:pointer}aside button:hover,aside button.active{background:#f2f4f7}main{padding:42px 24px;border-right:1px solid #e8ebef}header{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}h1{margin:0;font-size:24px}.actions{display:flex;gap:8px}.actions button,.quick button,.dialog-actions button{min-height:36px;border:0;border-radius:7px;background:#4f7ff0;color:#fff;padding:0 14px;cursor:pointer}.quick{display:grid;grid-template-columns:1fr auto;gap:8px;margin-bottom:12px}input,select,textarea{width:100%;min-height:38px;border:1px solid #e8ebef;border-radius:7px;background:#f7f8fa;padding:0 10px}textarea{min-height:86px;padding:10px}.task{display:grid;grid-template-columns:28px 1fr auto;align-items:center;min-height:44px;border-bottom:1px solid #e8ebef;border-radius:7px;padding:0 10px}.task:hover,.task.selected{background:#f7f8fa}.meta{display:flex;gap:8px;color:#77808c;font-size:12px}.chip{border-radius:999px;background:#eaf0ff;color:#4f7ff0;padding:2px 7px}.overdue{color:#ce3f3f}.detail{padding:58px 24px}.hidden{display:none!important}.title{font-size:22px;font-weight:800;background:#fff}.detail form{display:grid;gap:12px}fieldset{border:1px solid #e8ebef;border-radius:8px}.row{display:grid;grid-template-columns:auto 1fr 90px;gap:8px;align-items:center}dialog{border:0;border-radius:8px;width:min(620px,calc(100vw - 24px));box-shadow:0 14px 40px rgba(31,35,40,.16)}dialog form{display:grid;gap:12px}#account{color:#77808c;font-size:13px}@media(max-width:900px){.app{grid-template-columns:1fr}aside,.detail{display:none}main{padding:20px 12px}}`;

const APP_JS = `
let tasks=[];let settings={};let session=null;let selectedId="";let view="inbox";
const $=(id)=>document.getElementById(id);
const defaultSettings={browserEnabled:false,serverEnabled:false,wecomWebhook:"",feishuWebhook:"",feishuSecret:"",genericWebhook:"",resendApiKey:"",mailFrom:"",mailTo:""};
function id(){return "task-"+Date.now().toString(36)+"-"+Math.random().toString(36).slice(2,8)}
async function post(url,payload={}){const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});return r.json()}
function today(){return new Date().toISOString().slice(0,10)}
function parseDate(v){if(!v)return null;const [y,m,d]=v.split("-").map(Number);return new Date(y,m-1,d)}
function addInterval(date,every,unit){const d=new Date(date);if(unit==="day")d.setDate(d.getDate()+every);if(unit==="week")d.setDate(d.getDate()+every*7);if(unit==="month")d.setMonth(d.getMonth()+every);if(unit==="year")d.setFullYear(d.getFullYear()+every);return d}
function dateInput(date){return date.toISOString().slice(0,10)}
function repeatText(r){if(!r||r.mode==="none")return "";const u={day:"天",week:"周",month:"月",year:"年"};return (r.mode==="afterCompletion"?"完成重复":"固定重复")+" 每 "+r.every+" "+u[r.unit]}
function visibleTasks(){const t=parseDate(today());const w=addInterval(t,7,"day");return tasks.filter(task=>{if(view==="done")return task.completed;if(task.completed)return false;if(view==="today")return task.dueDate&&parseDate(task.dueDate)<=t;if(view==="week")return task.dueDate&&parseDate(task.dueDate)<=w;return true})}
function normalizeTask(task){return {id:id(),title:"",dueDate:"",dueTime:"",completed:false,completedAt:"",history:[],listName:"收集箱",priority:"none",tags:[],notes:"",subtasks:[],repeat:{mode:"none",every:1,unit:"day"},...task}}
function render(){renderCounts();renderTasks();renderDetail();renderSettings();$("account").textContent=session?(session.email||("portal:"+session.sub)):"未登录"}
function renderCounts(){const active=tasks.filter(t=>!t.completed);const td=parseDate(today());const w=addInterval(td,7,"day");$("allCount").textContent=active.length;$("todayCount").textContent=active.filter(t=>t.dueDate&&parseDate(t.dueDate)<=td).length;$("weekCount").textContent=active.filter(t=>t.dueDate&&parseDate(t.dueDate)<=w).length}
function renderTasks(){const root=$("tasks");root.innerHTML="";const list=visibleTasks();if(!list.length){root.innerHTML='<p class="meta">没有任务</p>';return}for(const task of list){const row=document.createElement("article");row.className="task"+(task.id===selectedId?" selected":"");const cb=document.createElement("input");cb.type="checkbox";cb.checked=task.completed;cb.onclick=(e)=>{e.stopPropagation();complete(task)};const title=document.createElement("div");title.textContent=task.title;const meta=document.createElement("div");meta.className="meta";if(task.repeat.mode!=="none"){const chip=document.createElement("span");chip.className="chip";chip.textContent=repeatText(task.repeat);meta.append(chip)}const d=document.createElement("span");d.textContent=task.completed?"已完成":(task.dueDate||"无日期");if(task.dueDate&&parseDate(task.dueDate)<parseDate(today()))d.className="overdue";meta.append(d);row.append(cb,title,meta);row.onclick=()=>{selectedId=task.id;render()};root.append(row)}}
function renderDetail(){const task=tasks.find(t=>t.id===selectedId);$("emptyDetail").classList.toggle("hidden",!!task);$("detailForm").classList.toggle("hidden",!task);if(!task)return;$("title").value=task.title;$("dueDate").value=task.dueDate;$("dueTime").value=task.dueTime;$("priority").value=task.priority;$("tags").value=task.tags.join(", ");$("notes").value=task.notes;$("repeatMode").value=task.repeat.mode;$("repeatEvery").value=task.repeat.every;$("repeatUnit").value=task.repeat.unit}
function renderSettings(){settings={...defaultSettings,...settings};$("serverEnabled").checked=!!settings.serverEnabled;$("wecomWebhook").value=settings.wecomWebhook||"";$("feishuWebhook").value=settings.feishuWebhook||"";$("feishuSecret").value=settings.feishuSecret||"";$("genericWebhook").value=settings.genericWebhook||"";$("resendApiKey").value=settings.resendApiKey||"";$("mailFrom").value=settings.mailFrom||"";$("mailTo").value=settings.mailTo||""}
async function sync(){await post("/api/sync",{tasks,settings})}
function updateTask(patch){const task=tasks.find(t=>t.id===selectedId);if(!task)return;Object.assign(task,patch);sync();render()}
function complete(task){if(!task.completed&&task.repeat.mode!=="none"){const base=task.repeat.mode==="afterCompletion"||!task.dueDate?new Date():parseDate(task.dueDate);task.dueDate=dateInput(addInterval(base,Number(task.repeat.every)||1,task.repeat.unit));task.history.push({completedAt:new Date().toLocaleString("zh-CN"),nextDueDate:task.dueDate})}else{task.completed=!task.completed;task.completedAt=task.completed?new Date().toLocaleString("zh-CN"):"";if(task.completed)task.history.push({completedAt:task.completedAt,nextDueDate:""})}sync();render()}
function readSettings(){settings={...defaultSettings,serverEnabled:$("serverEnabled").checked,wecomWebhook:$("wecomWebhook").value.trim(),feishuWebhook:$("feishuWebhook").value.trim(),feishuSecret:$("feishuSecret").value.trim(),genericWebhook:$("genericWebhook").value.trim(),resendApiKey:$("resendApiKey").value.trim(),mailFrom:$("mailFrom").value.trim(),mailTo:$("mailTo").value.trim()}}
async function boot(){const loaded=await post("/api/load",{});if(!loaded.ok){document.body.innerHTML='<main class="login"><h1>需要从 portal 登录</h1><p>请从 portal 应用入口打开 Todo CF。</p></main>';return}session=loaded.session;tasks=(loaded.tasks||[]).map(normalizeTask);settings={...defaultSettings,...loaded.settings};render();bind()}
function bind(){document.querySelectorAll("aside button[data-view]").forEach(b=>b.onclick=()=>{view=b.dataset.view;document.querySelectorAll("aside button[data-view]").forEach(x=>x.classList.remove("active"));b.classList.add("active");render()});$("quickAdd").onsubmit=(e)=>{e.preventDefault();const title=$("quickTitle").value.trim();if(!title)return;const task=normalizeTask({title,dueDate:today()});tasks.unshift(task);selectedId=task.id;$("quickTitle").value="";sync();render()};$("title").oninput=()=>updateTask({title:$("title").value});$("dueDate").onchange=()=>updateTask({dueDate:$("dueDate").value});$("dueTime").onchange=()=>updateTask({dueTime:$("dueTime").value});$("priority").onchange=()=>updateTask({priority:$("priority").value});$("tags").onchange=()=>updateTask({tags:$("tags").value.split(/[,，]/).map(t=>t.trim()).filter(Boolean)});$("notes").oninput=()=>updateTask({notes:$("notes").value});$("repeatMode").onchange=saveRepeat;$("repeatEvery").onchange=saveRepeat;$("repeatUnit").onchange=saveRepeat;$("deleteTask").onclick=()=>{tasks=tasks.filter(t=>t.id!==selectedId);selectedId="";sync();render()};$("syncBtn").onclick=sync;$("settingsBtn").onclick=()=>$("settingsDialog").showModal();$("closeSettings").onclick=()=>$("settingsDialog").close();$("settingsForm").onsubmit=(e)=>{e.preventDefault();readSettings();sync();$("settingsDialog").close()};$("testNotify").onclick=async()=>{readSettings();const r=await post("/api/test-notification",{settings});$("settingsStatus").textContent=r.ok?"测试已发送":"测试失败："+(r.errors||[]).join("; ")};$("logoutBtn").onclick=async()=>{await fetch("/api/logout",{method:"POST"});location.reload()}}
function saveRepeat(){updateTask({repeat:{mode:$("repeatMode").value,every:Math.max(1,Number($("repeatEvery").value)||1),unit:$("repeatUnit").value}})}
boot().catch(err=>{document.body.textContent=err.message});
`;
