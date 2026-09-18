/* ============================================================
   LanCloud 网盘前端逻辑
   ============================================================ */
"use strict";

// ---------- 工具 ----------
function toast(msg, type) {
  const box = document.getElementById("toast-box");
  const el = document.createElement("div");
  el.className = "toast" + (type ? " " + type : "");
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), type === "err" ? 4000 : 2600);
}

function fmtSize(n) {
  if (!n && n !== 0) return "-";
  if (n < 1024) return n + " B";
  const units = ["KB", "MB", "GB", "TB"];
  let v = n;
  for (const u of units) {
    v /= 1024;
    if (v < 1024) return v.toFixed(v < 10 ? 1 : 0) + " " + u;
  }
  return v.toFixed(1) + " PB";
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  const p = (x) => String(x).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) +
         " " + p(d.getHours()) + ":" + p(d.getMinutes());
}

async function api(url, opts) {
  const resp = await fetch(url, opts);
  let data = null;
  try { data = await resp.json(); } catch (e) { /* ignore */ }
  if (!resp.ok) {
    throw new Error((data && data.detail) || (data && data.error) || ("请求失败 " + resp.status));
  }
  return data;
}

// ---------- 图标 ----------
const EXT_CAT = {
  img: ["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico"],
  vid: ["mp4", "webm", "mkv", "mov", "avi", "m4v"],
  aud: ["mp3", "wav", "ogg", "m4a", "flac", "aac", "opus"],
  doc: ["doc", "docx", "ppt", "pptx", "xls", "xlsx", "pdf"],
  txt: ["txt", "md", "json", "js", "py", "html", "css", "xml", "yml", "yaml", "log", "ini", "conf", "sh", "bat", "c", "cpp", "h", "java", "go", "rs"],
  arc: ["zip", "rar", "7z", "tar", "gz", "xz", "bz2"],
  code: [],
};
const EXT_COLOR = { img: "green", vid: "purple", aud: "cyan", doc: "red", arc: "orange", txt: "gray", code: "gray" };

function typeOf(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  for (const k in EXT_CAT) if (EXT_CAT[k].includes(ext)) return k;
  return "file";
}

function fileIcon(name, isDir, size) {
  if (isDir) {
    return '<span class="ico ico-folder"><svg width="46" height="46" viewBox="0 0 24 24" fill="currentColor"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg></span>';
  }
  const t = typeOf(name);
  const label = t === "file" ? (name.split(".").pop() || "?") : t.toUpperCase();
  return `<span class="ico-type ${EXT_COLOR[t] || "gray"}">${label.slice(0, 4)}</span>`;
}

// ---------- 登录 ----------
let ME = null;

function switchLoginTab(mode) {
  document.getElementById("tab-login").className = mode === "login" ? "active" : "";
  document.getElementById("tab-reg").className = mode === "reg" ? "active" : "";
  document.getElementById("login-form").style.display = mode === "login" ? "" : "none";
  document.getElementById("reg-form").style.display = mode === "reg" ? "" : "none";
}

async function doLogin(e) {
  e.preventDefault();
  try {
    await api("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: document.getElementById("login-user").value.trim(),
                             password: document.getElementById("login-pass").value }),
    });
    toast("登录成功", "ok");
    await initApp();
  } catch (err) { toast(err.message, "err"); }
  return false;
}

async function doRegister(e) {
  e.preventDefault();
  const u = document.getElementById("reg-user").value.trim();
  const p = document.getElementById("reg-pass").value;
  try {
    await api("/api/auth/register", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p }),
    });
    await api("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p }),
    });
    toast("注册成功", "ok");
    await initApp();
  } catch (err) { toast(err.message, "err"); }
  return false;
}

async function doLogout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) {}
  location.reload();
}

// ---------- 应用初始化 ----------
async function initApp() {
  try {
    ME = await api("/api/auth/me");
  } catch (e) {
    document.getElementById("login-view").style.display = "flex";
    return;
  }
  document.getElementById("login-view").style.display = "none";
  document.getElementById("app-view").classList.add("show");
  document.getElementById("user-name").textContent = ME.username;
  document.getElementById("user-role").textContent = ME.is_admin ? "管理员" : "普通用户";
  document.getElementById("user-avatar").textContent = ME.username.slice(0, 1).toUpperCase();
  if (ME.is_admin) document.getElementById("nav-admin").style.display = "";
  updateUsage();
  loadFiles("");
}

function updateUsage() {
  if (!ME) return;
  const pct = Math.min(100, Math.round(ME.size / (500 * 1024 * 1024) * 100));
  document.getElementById("usage-bar").style.width = pct + "%";
  document.getElementById("usage-txt").textContent = `已用 ${fmtSize(ME.size)} · ${ME.files} 个文件`;
}

// ---------- 视图切换 ----------
function switchView(v) {
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.view === v));
  ["files", "shares", "trash"].forEach((k) => {
    document.getElementById("view-" + k).style.display = k === v ? "" : "none";
  });
  if (v === "shares") loadShares();
  if (v === "trash") loadTrash();
  if (v === "files") loadFiles(STATE.path);
}

// ---------- 文件浏览 ----------
const STATE = { path: "", view: "grid", searchQ: null };

function crumbHtml(path) {
  const parts = path ? path.split("/") : [];
  let html = '<a href="#" onclick="return goUp(\'\')">网盘根目录</a>';
  let acc = "";
  parts.forEach((p, i) => {
    acc = acc ? acc + "/" + p : p;
    const isLast = i === parts.length - 1;
    html += '<span class="sep">/</span>';
    html += isLast
      ? '<span class="cur">' + esc(p) + "</span>"
      : '<a href="#" onclick="return goUp(\'' + acc + '\')">' + esc(p) + "</a>";
  });
  return html;
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function goUp(p) { STATE.path = p; loadFiles(p); return false; }

async function loadFiles(path) {
  STATE.path = path || "";
  STATE.searchQ = null;
  document.getElementById("search-input").value = "";
  document.getElementById("crumbs").innerHTML = crumbHtml(STATE.path);
  let items;
  try {
    const data = await api("/api/fs/list?path=" + encodeURIComponent(STATE.path));
    items = data.items;
  } catch (e) {
    items = [];
    toast(e.message, "err");
  }
  renderItems(items);
  document.getElementById("dir-count").textContent = items.length ? `${items.length} 个项目` : "";
}

function renderItems(items) {
  const grid = document.getElementById("file-grid");
  const tbody = document.getElementById("file-list-body");
  if (!items.length) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1"><div class="empty-icon">▱</div>这里空空如也<br>点击右上角「上传」或直接拖拽文件进来</div>';
    tbody.innerHTML = "";
    return;
  }
  grid.innerHTML = items.map(cardHtml).join("");
  tbody.innerHTML = items.map((it) => `<tr class="file-row" ondblclick="openItem('${esc(it.path)}',${it.is_dir})">
      <td><div class="name-cell">${fileIcon(it.name, it.is_dir, it.size)}<span>${esc(it.name)}</span></div></td>
      <td>${it.is_dir ? "—" : fmtSize(it.size)}</td>
      <td>${fmtTime(it.mtime)}</td>
      <td><div class="l-actions">
        ${it.is_dir ? "" : `<button title="下载" onclick="event.stopPropagation();downloadItem('${esc(it.path)}')">下载</button>`}
        <button title="分享" onclick="event.stopPropagation();shareItem('${esc(it.path)}')">分享</button>
        <button title="重命名" onclick="event.stopPropagation();renameItem('${esc(it.path)}')">重命名</button>
        <button title="移动" onclick="event.stopPropagation();moveItem('${esc(it.path)}')">移动</button>
        <button title="删除" onclick="event.stopPropagation();deleteItem('${esc(it.path)}')">删除</button>
      </div></td></tr>`).join("");
}

function cardHtml(it) {
  const p = esc(it.path), n = esc(it.name);
  return `<div class="file-card" ondblclick="openItem('${p}',${it.is_dir})">
    <div class="fc-actions">
      ${it.is_dir ? "" : `<button title="下载" onclick="downloadItem('${p}')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 3v12m0 0l-5-5m5 5l5-5M4 21h16"/></svg></button>`}
      <button title="分享" onclick="shareItem('${p}')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M8.6 10.5l6.8-4"/></svg></button>
      <button title="重命名" onclick="renameItem('${p}')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M17 3l4 4L8 20l-5 1 1-5z"/></svg></button>
      <button title="删除" onclick="deleteItem('${p}')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/></svg></button>
    </div>
    <div class="fc-icon">${fileIcon(it.name, it.is_dir, it.size)}</div>
    <div class="fc-name" title="${n}">${n}</div>
    <div class="fc-meta">${it.is_dir ? "文件夹" : fmtSize(it.size)} · ${fmtTime(it.mtime).slice(5, 16)}</div>
  </div>`;
}

function setView(v) {
  STATE.view = v;
  document.getElementById("vt-grid").className = v === "grid" ? "active" : "";
  document.getElementById("vt-list").className = v === "list" ? "active" : "";
  document.getElementById("file-grid").style.display = v === "grid" ? "" : "none";
  document.getElementById("file-list").style.display = v === "list" ? "" : "none";
}

function openItem(path, isDir) {
  if (isDir) { STATE.path = path; loadFiles(path); return; }
  previewItem(path);
}

// ---------- 上传 ----------
function handleSelect(e) {
  uploadFiles(e.target.files);
  e.target.value = "";
}

function setupDragDrop() {
  const zone = document.getElementById("drop-zone");
  let depth = 0;
  window.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; document.body.classList.add("dragging"); });
  window.addEventListener("dragleave", (e) => { e.preventDefault(); depth--; if (!depth) document.body.classList.remove("dragging"); });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault(); depth = 0;
    document.body.classList.remove("dragging");
    if (e.dataTransfer && e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  });
  zone.addEventListener("dragenter", () => zone.classList.add("on"));
  zone.addEventListener("dragleave", () => zone.classList.remove("on"));
}

function uploadFiles(fileList) {
  const files = Array.from(fileList);
  if (!files.length) return;
  const total = files.length;
  let done = 0;
  showModal(`
    <div class="modal" style="max-width:420px">
      <div class="modal-head"><h3>正在上传 ${total} 个文件</h3><button class="modal-close" onclick="closeModal()">×</button></div>
      <div class="modal-body">
        <div class="progress-wrap"><div class="bar"><i id="up-bar"></i></div><div class="txt" id="up-txt">准备中…</div></div>
      </div>
    </div>`);
  const bar = document.getElementById("up-bar");
  const txt = document.getElementById("up-txt");
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f, f.name));
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/fs/upload?path=" + encodeURIComponent(STATE.path));
  xhr.withCredentials = true;
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      bar.style.width = pct + "%";
      txt.textContent = pct + "%";
    }
  };
  xhr.onload = async () => {
    try {
      const data = JSON.parse(xhr.responseText);
      if (xhr.status >= 400) throw new Error(data.detail || data.error || "上传失败");
      txt.textContent = "上传完成 ✓";
      setTimeout(() => { closeModal(); loadFiles(STATE.path); updateUsage(); }, 600);
    } catch (err) {
      txt.textContent = "上传失败：" + err.message;
      setTimeout(() => closeModal(), 2000);
    }
  };
  xhr.onerror = () => { txt.textContent = "网络错误，上传失败"; setTimeout(() => closeModal(), 2000); };
  xhr.send(fd);
}

// ---------- 文件操作 ----------
function downloadItem(path) {
  window.location.href = "/api/fs/download?path=" + encodeURIComponent(path);
}

async function shareItem(path) {
  try {
    const rec = await api("/api/share", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const url = location.origin + "/s/" + rec.token;
    showModal(`
      <div class="modal" style="max-width:460px">
        <div class="modal-head"><h3>分享链接已生成</h3><button class="modal-close" onclick="closeModal()">×</button></div>
        <div class="modal-body">
          <div class="form-row"><label>分享链接（局域网内任何设备打开即可访问）</label>
            <input class="input" id="share-url" readonly value="${url}">
          </div>
          <div class="form-row"><label>路径：${esc(path)}</label></div>
          <div class="notice info">提示：对方需与你在同一局域网内；链接无需对方登录即可访问。</div>
        </div>
        <div class="modal-foot">
          <button class="btn" onclick="closeModal()">关闭</button>
          <button class="btn primary" onclick="copyShareUrl()">复制链接</button>
        </div>
      </div>`);
  } catch (e) { toast(e.message, "err"); }
}

function copyShareUrl() {
  const input = document.getElementById("share-url");
  if (!input) return;
  navigator.clipboard.writeText(input.value).then(
    () => toast("链接已复制", "ok"),
    () => { input.select(); document.execCommand("copy"); toast("链接已复制", "ok"); });
}

async function renameItem(path) {
  const name = path.split("/").pop();
  showModal(`
    <div class="modal" style="max-width:420px">
      <div class="modal-head"><h3>重命名</h3><button class="modal-close" onclick="closeModal()">×</button></div>
      <div class="modal-body">
        <div class="form-row"><label>新名称</label><input class="input" id="rename-input" value="${esc(name)}"></div>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="closeModal()">取消</button>
        <button class="btn primary" onclick="doRename('${esc(path)}')">确定</button>
      </div>
    </div>`);
  document.getElementById("rename-input").focus();
  document.getElementById("rename-input").select();
}

async function doRename(path) {
  const newName = document.getElementById("rename-input").value.trim();
  if (!newName) { toast("名称不能为空", "err"); return; }
  try {
    await api("/api/fs/rename", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, new_name: newName }),
    });
    closeModal(); toast("重命名成功", "ok"); loadFiles(STATE.path);
  } catch (e) { toast(e.message, "err"); }
}

// 移动
let MOVE_STATE = { path: "", target: "" };

function moveItem(path) {
  MOVE_STATE = { path: "", target: path };
  renderMoveModal();
}

async function renderMoveModal() {
  let dirs = [];
  try {
    const data = await api("/api/fs/list?path=" + encodeURIComponent(MOVE_STATE.path));
    dirs = data.items.filter((i) => i.is_dir);
  } catch (e) {}
  const parts = MOVE_STATE.path ? MOVE_STATE.path.split("/") : [];
  let crumbs = '<button class="btn sm" onclick="moveNav(\'\')">根目录</button>';
  let acc = "";
  parts.forEach((p) => {
    acc = acc ? acc + "/" + p : p;
    crumbs += ' <span style="color:var(--text-2)">/</span> <button class="btn sm" onclick="moveNav(\'' + acc + '\')">' + esc(p) + "</button>";
  });
  showModal(`
    <div class="modal" style="max-width:440px">
      <div class="modal-head"><h3>移动到…</h3><button class="modal-close" onclick="closeModal()">×</button></div>
      <div class="modal-body">
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">${crumbs}</div>
        ${dirs.length ? `<div style="display:flex;flex-direction:column;gap:6px;max-height:280px;overflow:auto">
          ${dirs.map((d) => `<button class="btn" style="justify-content:flex-start" onclick="moveNav('${esc(d.path)}')"><svg width="15" height="15" viewBox="0 0 24 24" fill="#F5B342" style="margin-right:8px"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>${esc(d.name)}</button>`).join("")}
        </div>` : '<div class="empty" style="padding:24px">当前目录下没有子文件夹</div>'}
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="closeModal()">取消</button>
        <button class="btn primary" onclick="doMove()">移动到此处</button>
      </div>
    </div>`);
}

function moveNav(p) { MOVE_STATE.path = p; renderMoveModal(); }

async function doMove() {
  try {
    await api("/api/fs/move", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: MOVE_STATE.target, dest: MOVE_STATE.path }),
    });
    closeModal(); toast("移动成功", "ok"); loadFiles(STATE.path);
  } catch (e) { toast(e.message, "err"); }
}

async function deleteItem(path) {
  if (!confirm("确定删除「" + path.split("/").pop() + "」吗？\n删除后可在回收站恢复。")) return;
  try {
    await api("/api/fs/delete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    toast("已移入回收站", "ok"); loadFiles(STATE.path);
  } catch (e) { toast(e.message, "err"); }
}

async function openNewFolder() {
  showModal(`
    <div class="modal" style="max-width:400px">
      <div class="modal-head"><h3>新建文件夹</h3><button class="modal-close" onclick="closeModal()">×</button></div>
      <div class="modal-body">
        <div class="form-row"><label>文件夹名称</label><input class="input" id="mkdir-input" placeholder="例如：家庭相册"></div>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="closeModal()">取消</button>
        <button class="btn primary" onclick="doMkdir()">创建</button>
      </div>
    </div>`);
  document.getElementById("mkdir-input").focus();
}

async function doMkdir() {
  const name = document.getElementById("mkdir-input").value.trim();
  if (!name) { toast("名称不能为空", "err"); return; }
  try {
    await api("/api/fs/mkdir", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: STATE.path, name }),
    });
    closeModal(); toast("创建成功", "ok"); loadFiles(STATE.path);
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 预览 ----------
function previewItem(path) {
  const name = path.split("/").pop();
  const t = typeOf(name);
  const dl = "/api/fs/download?path=" + encodeURIComponent(path);
  const dlI = dl + "&inline=1";
  let body = "";
  if (t === "img") body = `<div class="preview-media"><img src="${dlI}" alt="${esc(name)}"></div>`;
  else if (t === "vid") body = `<div class="preview-media"><video controls src="${dlI}" style="max-width:100%"></video></div>`;
  else if (t === "aud") body = `<div class="preview-media"><audio controls src="${dlI}"></audio></div>`;
  else if (t === "txt") body = `<div class="preview-text" id="preview-text">加载中…</div>`;
  else if (t === "doc" && /\.pdf$/i.test(name)) body = `<div class="preview-media" style="align-items:flex-start"><iframe src="${dlI}" style="width:100%;height:62vh;border:none"></iframe></div>`;
  else body = `<div class="preview-file"><div class="big-icon">${fileIcon(name, false, 0)}</div>
      <div class="pf-name">${esc(name)}</div>
      <div class="pf-size">此类型不支持在线预览，请下载后查看</div>
      <a class="btn primary" href="${dl}">下载文件</a></div>`;
  showModal(`
    <div class="modal" style="max-width:640px">
      <div class="modal-head"><h3 style="word-break:break-all">${esc(name)}</h3>
        <div style="display:flex;gap:8px">
          <a class="btn sm" href="${dl}">下载</a>
          <button class="modal-close" onclick="closeModal()">×</button>
        </div></div>
      <div class="modal-body">${body}</div>
    </div>`);
  if (t === "txt") loadPreviewText(dlI);
}

async function loadPreviewText(url) {
  try {
    const resp = await fetch(url);
    const text = await resp.text();
    const el = document.getElementById("preview-text");
    if (el) el.textContent = text.length > 500000 ? text.slice(0, 500000) + "\n\n……（文件过大，已截断显示）" : text;
  } catch (e) {
    const el = document.getElementById("preview-text");
    if (el) el.textContent = "预览加载失败";
  }
}

// ---------- 分享管理 ----------
async function loadShares() {
  let items = [];
  try { items = (await api("/api/share/list")).items; } catch (e) {}
  const body = document.getElementById("shares-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5"><div class="empty">还没有分享，回到「我的网盘」右键文件点击分享试试</div></td></tr>';
    return;
  }
  body.innerHTML = items.map((s) => `
    <tr>
      <td>${esc(s.path.split("/").pop() || s.path)}</td>
      <td style="color:var(--text-2)">${esc(s.path || "/")}</td>
      <td style="color:var(--text-2)">${fmtTime(s.created)}</td>
      <td><a href="#" onclick="copyLink('${s.token}');return false" style="color:var(--primary)">复制链接</a></td>
      <td><div class="row-actions">
        <button class="btn sm danger" onclick="deleteShare('${s.token}')">取消分享</button>
      </div></td>
    </tr>`).join("");
}

function copyLink(token) {
  const url = location.origin + "/s/" + token;
  navigator.clipboard.writeText(url).then(() => toast("链接已复制", "ok"),
    () => toast(url, "ok"));
}

async function deleteShare(token) {
  if (!confirm("确定取消该分享吗？")) return;
  try { await api("/api/share/" + token, { method: "DELETE" }); toast("已取消分享", "ok"); loadShares(); }
  catch (e) { toast(e.message, "err"); }
}

// ---------- 回收站 ----------
async function loadTrash() {
  let items = [];
  try { items = (await api("/api/trash")).items; } catch (e) {}
  const body = document.getElementById("trash-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="4"><div class="empty">回收站是空的</div></td></tr>';
    return;
  }
  body.innerHTML = items.map((it) => `
    <tr>
      <td>${esc(it.trash_name)}</td>
      <td>${it.is_dir ? "文件夹" : "文件"}</td>
      <td style="color:var(--text-2)">${fmtTime(it.time)}</td>
      <td><div class="row-actions">
        <button class="btn sm" onclick="restoreTrash('${esc(it.trash_name)}')">恢复</button>
        <button class="btn sm danger" onclick="deleteForever('${esc(it.trash_name)}')">彻底删除</button>
      </div></td>
    </tr>`).join("");
}

async function restoreTrash(name) {
  try {
    await api("/api/trash/restore", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trash_name: name }),
    });
    toast("已恢复", "ok"); loadTrash();
  } catch (e) { toast(e.message, "err"); }
}

async function deleteForever(name) {
  if (!confirm("彻底删除后不可恢复，确定吗？")) return;
  try { await api("/api/trash/delete-forever", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trash_name: name }) }); loadTrash(); }
  catch (e) { toast(e.message, "err"); }
}

async function emptyTrash() {
  if (!confirm("确定清空回收站吗？清空后不可恢复！")) return;
  try { await api("/api/trash/empty", { method: "POST" }); toast("回收站已清空", "ok"); loadTrash(); }
  catch (e) { toast(e.message, "err"); }
}

// ---------- 搜索 ----------
async function doSearch() {
  const q = document.getElementById("search-input").value.trim();
  if (!q) { loadFiles(STATE.path); return; }
  try {
    const data = await api("/api/fs/search?q=" + encodeURIComponent(q));
    const items = data.items;
    document.getElementById("crumbs").innerHTML = `搜索「<span class="cur">${esc(q)}</span>」· ${items.length} 个结果 <a href="#" style="margin-left:8px;font-size:13px" onclick="return loadFiles(STATE.path)">← 返回</a>`;
    renderItems(items);
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 模态框 ----------
function showModal(html) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="modal-mask show" onclick="if(event.target===this)closeModal()">${html}</div>`;
}
function closeModal() { document.getElementById("modal-root").innerHTML = ""; }

// ---------- 启动 ----------
setupDragDrop();
initApp();
