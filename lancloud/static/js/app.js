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
  txt: ["txt", "md", "json", "js", "py", "html", "css", "xml", "yml", "yaml", "log", "ini", "conf", "sh", "bat", "c", "cpp", "h", "java", "go", "rs", "csv", "sql", "toml", "env"],
  arc: ["zip", "rar", "7z", "tar", "gz", "xz", "bz2"],
  code: [],
};
// ---------- Phosphor 开源图标（MIT，regular 字重统一） ----------
const SVG = (p, w = 44) =>
  `<svg width="${w}" height="${w}" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true">${p}</svg>`;
const ICON = {
  folder: '<path d="M245,110.64A16,16,0,0,0,232,104H216V88a16,16,0,0,0-16-16H130.67L102.94,51.2a16.14,16.14,0,0,0-9.6-3.2H40A16,16,0,0,0,24,64V208h0a8,8,0,0,0,8,8H211.1a8,8,0,0,0,7.59-5.47Z"/>',
  file: '<path d="M213.66,82.34l-56-56A8,8,0,0,0,152,24H56A16,16,0,0,0,40,40V216a16,16,0,0,0,16,16H200a16,16,0,0,0,16-16V88A8,8,0,0,0,213.66,82.34ZM160,51.31,188.69,80H160ZM200,216H56V40h88V88a8,8,0,0,0,8,8h48V216Z"/>',
  image: '<path d="M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM48,48H208v77.38l-24.69-24.7a16,16,0,0,0-22.62,0L53.37,208H48ZM208,208H76l96-96,36,36v60ZM96,120A24,24,0,1,0,72,96,24,24,0,0,0,96,120Zm0-32a8,8,0,1,1-8,8A8,8,0,0,1,96,88Z"/>',
  play: '<path d="M232.4,114.49,88.32,26.35a16,16,0,0,0-16.2-.3A15.86,15.86,0,0,0,64,39.87V216.13A15.94,15.94,0,0,0,80,232a16.07,16.07,0,0,0,8.36-2.35L232.4,141.51a15.81,15.81,0,0,0,0-27ZM80,215.94V40l143.83,88Z"/>',
  download: '<path d="M224,144v64a8,8,0,0,1-8,8H40a8,8,0,0,1-8-8V144a8,8,0,0,1,16,0v56H208V144a8,8,0,0,1,16,0Zm-101.66,5.66a8,8,0,0,0,11.32,0l40-40a8,8,0,0,0-11.32-11.32L136,124.69V32a8,8,0,0,0-16,0v92.69L93.66,98.34a8,8,0,0,0-11.32,11.32Z"/>',
  share: '<path d="M176,160a39.89,39.89,0,0,0-28.62,12.09l-46.1-29.63a39.8,39.8,0,0,0,0-28.92l46.1-29.63a40,40,0,1,0-8.66-13.45l-46.1,29.63a40,40,0,1,0,0,55.82l46.1,29.63A40,40,0,1,0,176,160Zm0-128a24,24,0,1,1-24,24A24,24,0,0,1,176,32ZM64,152a24,24,0,1,1,24-24A24,24,0,0,1,64,152Zm112,72a24,24,0,1,1,24-24A24,24,0,0,1,176,224Z"/>',
  pencil: '<path d="M227.31,73.37,182.63,28.68a16,16,0,0,0-22.63,0L36.69,152A15.86,15.86,0,0,0,32,163.31V208a16,16,0,0,0,16,16H92.69A15.86,15.86,0,0,0,104,219.31L227.31,96a16,16,0,0,0,0-22.63ZM92.69,208H48V163.31l88-88L180.69,120ZM192,108.68,147.31,64l24-24L216,84.68Z"/>',
  trash: '<path d="M216,48H176V40a24,24,0,0,0-24-24H104A24,24,0,0,0,80,40v8H40a8,8,0,0,0,0,16h8V208a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V64h8a8,8,0,0,0,0-16ZM96,40a8,8,0,0,1,8-8h48a8,8,0,0,1,8,8v8H96Zm96,168H64V64H192ZM112,104v64a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Zm48,0v64a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Z"/>',
  up: '<path d="M224,144v64a8,8,0,0,1-8,8H40a8,8,0,0,1-8-8V144a8,8,0,0,1,16,0v56H208V144a8,8,0,0,1,16,0ZM93.66,77.66,120,51.31V144a8,8,0,0,0,16,0V51.31l26.34,26.35a8,8,0,0,0,11.32-11.32l-40-40a8,8,0,0,0-11.32,0l-40,40A8,8,0,0,0,93.66,77.66Z"/>',
};
const S_ICO = (key, s = 14) => SVG(ICON[key], s);

function typeOf(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  for (const k in EXT_CAT) if (EXT_CAT[k].includes(ext)) return k;
  return "file";
}

function fileIcon(name, isDir) {
  if (isDir) return `<span class="ico ico-folder">${SVG(ICON.folder)}</span>`;
  const t = typeOf(name);
  if (t === "img") return `<span class="ico ico-type green">${SVG(ICON.image, 30)}</span>`;
  if (t === "vid") return `<span class="ico ico-type cyan">${SVG(ICON.play, 30)}</span>`;
  if (t === "aud") return `<span class="ico ico-type orange">${SVG(ICON.play, 30)}</span>`;
  if (t === "doc") return `<span class="ico ico-type purple">${SVG(ICON.file, 30)}</span>`;
  if (t === "arc") return `<span class="ico ico-type orange">${SVG(ICON.file, 30)}</span>`;
  return `<span class="ico ico-type gray">${SVG(ICON.file, 30)}</span>`;
}

// 当前目录项目缓存（供详情侧栏使用）
let LAST_ITEMS = [];
// 多选集合
const SEL = new Set();

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
  if (!ME.allow_register) document.getElementById("tab-reg").style.display = "none";
  if (!ME.can_share) {
    document.querySelector('.nav-item[data-view="shares"]').style.display = "none";
  }
  updateUsage();
  loadFiles("");
  loadMountsRoot();
}

function updateUsage() {
  if (!ME) return;
  let txt = `已用 ${fmtSize(ME.size)} · ${ME.files} 个文件`;
  let pct = 0;
  if (ME.quota_mb > 0) {
    pct = Math.min(100, Math.round(ME.size / (ME.quota_mb * 1024 * 1024) * 100));
    txt += ` / 配额 ${ME.quota_mb} MB`;
    if (pct >= 90) txt += "（空间即将用尽）";
  } else if (ME.is_admin) {
    // 管理员不限
  }
  document.getElementById("usage-bar").style.width = pct + "%";
  document.getElementById("usage-txt").textContent = txt;
}

// ---------- 视图切换 ----------
function switchView(v) {
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.view === v));
  ["files", "mounts", "shares", "trash"].forEach((k) => {
    document.getElementById("view-" + k).style.display = k === v ? "" : "none";
  });
  if (v === "shares") loadShares();
  if (v === "trash") loadTrash();
  if (v === "files") loadFiles(STATE.path);
  if (v === "mounts") loadMountsRoot();
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
  LAST_ITEMS = items;
  SEL.clear(); updateBatchBar();
  const grid = document.getElementById("file-grid");
  const tbody = document.getElementById("file-list-body");
  if (!items.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="empty-icon">${SVG(ICON.folder, 56)}</div>这里空空如也<br>点击右上角「上传」或直接拖拽文件进来</div>`;
    tbody.innerHTML = "";
    return;
  }
  grid.innerHTML = items.map(cardHtml).join("");
  tbody.innerHTML = items.map((it) => `<tr class="file-row" data-path="${esc(it.path)}" ondblclick="openItem('${esc(it.path)}',${it.is_dir})">
      <td><div class="name-cell">${fileIcon(it.name, it.is_dir)}<span>${esc(it.name)}</span></div></td>
      <td>${it.is_dir ? "—" : fmtSize(it.size)}</td>
      <td>${fmtTime(it.mtime)}</td>
      <td><div class="l-actions">
        ${it.is_dir ? `<button title="打包下载" onclick="event.stopPropagation();zipItem('${esc(it.path)}')">${S_ICO("download",15)}</button>` : `<button title="下载" onclick="event.stopPropagation();downloadItem('${esc(it.path)}')">${S_ICO("download",15)}</button>`}
        ${it.is_dir ? "" : `<button title="在线编辑" onclick="event.stopPropagation();editItem('${esc(it.path)}')">${S_ICO("pencil",15)}</button>`}
        <button title="详情" onclick="event.stopPropagation();openDetail('${esc(it.path)}')">${S_ICO("file",15)}</button>
        <button title="分享" onclick="event.stopPropagation();shareItem('${esc(it.path)}')">${S_ICO("share",15)}</button>
        <button title="重命名" onclick="event.stopPropagation();renameItem('${esc(it.path)}')">${S_ICO("pencil",15)}</button>
        <button title="移动" onclick="event.stopPropagation();moveItem('${esc(it.path)}')">${SVG(ICON.folder,15)}</button>
        <button title="删除" onclick="event.stopPropagation();deleteItem('${esc(it.path)}')">${S_ICO("trash",15)}</button>
      </div></td></tr>`).join("");
}

function cardHtml(it) {
  const p = esc(it.path), n = esc(it.name);
  const sel = SEL.has(it.path) ? " sel" : "";
  return `<div class="file-card${sel}" data-path="${p}" onclick="toggleSelect('${p}')" ondblclick="openItem('${p}',${it.is_dir})">
    <div class="fc-actions">
      ${it.is_dir ? `<button title="打包下载" onclick="event.stopPropagation();zipItem('${p}')">${S_ICO("download",13)}</button>`
        : `<button title="下载" onclick="event.stopPropagation();downloadItem('${p}')">${S_ICO("download",13)}</button>`}
      <button title="详情" onclick="event.stopPropagation();openDetail('${p}')">${S_ICO("file",13)}</button>
      <button title="分享" onclick="event.stopPropagation();shareItem('${p}')">${S_ICO("share",13)}</button>
      <button title="删除" onclick="event.stopPropagation();deleteItem('${p}')">${S_ICO("trash",13)}</button>
    </div>
    <div class="fc-icon">${fileIcon(it.name, it.is_dir)}</div>
    <div class="fc-name" title="${n}">${n}</div>
    <div class="fc-meta">${it.is_dir ? "文件夹" : fmtSize(it.size)} · ${fmtTime(it.mtime).slice(5, 16)}</div>
  </div>`;
}

// ---------- 多选 ----------
function toggleSelect(path) {
  if (SEL.has(path)) SEL.delete(path); else SEL.add(path);
  document.querySelectorAll(".file-card").forEach((c) => {
    if (c.dataset.path) c.classList.toggle("sel", SEL.has(c.dataset.path));
  });
  document.querySelectorAll(".file-list .file-row").forEach((r) => {
    if (r.dataset.path) r.classList.toggle("sel", SEL.has(r.dataset.path));
  });
  updateBatchBar();
}
function updateBatchBar() {
  const bar = document.getElementById("batch-bar");
  if (!bar) return;
  document.getElementById("bc-count").textContent = "已选 " + SEL.size + " 项";
  bar.classList.toggle("show", SEL.size > 0);
}
function clearSelection() { SEL.clear(); document.querySelectorAll(".sel").forEach((c) => c.classList.remove("sel")); updateBatchBar(); }
async function batchDelete() {
  if (!SEL.size) return;
  if (!confirm("确认删除选中的 " + SEL.size + " 个项目？删除后进入回收站。")) return;
  const paths = Array.from(SEL);
  let ok = 0;
  for (const p of paths) {
    try { await api("/api/fs/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: p }) }); ok++; }
    catch (e) { toast(e.message, "err"); }
  }
  clearSelection(); toast("已删除 " + ok + " 项", "ok"); loadFiles(STATE.path);
}
function batchDownload() {
  if (!SEL.size) return;
  // 逐个触发浏览器下载（小文件适用）；文件夹走 zip
  Array.from(SEL).forEach((p, i) => {
    setTimeout(() => {
      const it = LAST_ITEMS.find((x) => x.path === p);
      if (it && it.is_dir) zipItem(p); else downloadItem(p);
    }, i * 350);
  });
  toast("开始下载 " + SEL.size + " 个项目", "ok");
}

// ---------- 详情侧栏 ----------
function openDetail(path) {
  const it = LAST_ITEMS.find((x) => x.path === path);
  if (!it) return;
  document.getElementById("dp-icon").innerHTML = fileIcon(it.name, it.is_dir);
  document.getElementById("dp-name").textContent = it.name;
  document.getElementById("dp-type").textContent = it.is_dir ? "文件夹" : (typeOf(it.name) + " 文件");
  document.getElementById("dp-size").textContent = it.is_dir ? "—" : fmtSize(it.size);
  document.getElementById("dp-mtime").textContent = fmtTime(it.mtime);
  document.getElementById("dp-path").textContent = it.path || "/";
  const openBtn = document.getElementById("dp-open");
  openBtn.onclick = () => { closeDetail(); openItem(it.path, it.is_dir); };
  document.getElementById("dp-close").onclick = closeDetail;
  document.getElementById("detail-panel").classList.add("show");
}
function closeDetail() { document.getElementById("detail-panel").classList.remove("show"); }

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

function zipItem(path) {
  window.location.href = "/api/fs/zip?path=" + encodeURIComponent(path);
}

function zipCurrent() {
  if (!STATE.path) { toast("当前已在根目录", "err"); return; }
  zipItem(STATE.path);
}

async function shareItem(path) {
  showModal(`
    <div class="modal" style="max-width:480px">
      <div class="modal-head"><h3>创建分享链接</h3><button class="modal-close" onclick="closeModal()">×</button></div>
      <div class="modal-body">
        <div class="form-row"><label>分享内容</label><div style="font-size:13.5px">${esc(path.split("/").pop() || path)}</div></div>
        <div class="form-row"><label>访问限制</label>
          <label style="display:flex;align-items:center;gap:8px;font-size:13.5px;margin-bottom:8px">
            <input type="checkbox" id="share-login" style="width:16px;height:16px"> 需要登录后才能访问（对方需有本网盘账号）
          </label>
          <div style="display:flex;align-items:center;gap:10px;font-size:13.5px">
            <span>链接有效期：</span>
            <select class="select" id="share-expire" style="width:auto">
              <option value="0">永久有效</option>
              <option value="1">1 天</option>
              <option value="7">7 天</option>
              <option value="30">30 天</option>
            </select>
          </div>
        </div>
        <div class="notice info" style="margin:0">局域网内任何设备打开链接即可访问；选择「需要登录」后，未登录访客会先看到登录页。</div>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="closeModal()">取消</button>
        <button class="btn primary" onclick="doShare('${esc(path)}')">生成链接</button>
      </div>
    </div>`);
}

async function doShare(path) {
  const require_login = document.getElementById("share-login").checked;
  const expire_days = parseInt(document.getElementById("share-expire").value || "0", 10);
  try {
    const rec = await api("/api/share", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, require_login, expire_days }),
    });
    const url = location.origin + "/s/" + rec.token;
    closeModal();
    showModal(`
      <div class="modal" style="max-width:460px">
        <div class="modal-head"><h3>分享链接已生成</h3><button class="modal-close" onclick="closeModal()">×</button></div>
        <div class="modal-body">
          <div class="form-row"><label>分享链接（局域网内任何设备打开即可访问）</label>
            <input class="input" id="share-url" readonly value="${url}">
          </div>
          <div class="form-row"><label>路径：${esc(path)}</label></div>
          <div class="notice info">${require_login ? "已开启强制登录：访客需先登录网盘账号。" : "免登录访问。"}${expire_days ? ` 有效期 ${expire_days} 天。` : " 永久有效。"}</div>
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
  const editBtn = t === "txt" ? `<button class="btn sm" onclick="editItem('${esc(path)}')">编辑</button>` : "";
  showModal(`
    <div class="modal" style="max-width:640px">
      <div class="modal-head"><h3 style="word-break:break-all">${esc(name)}</h3>
        <div style="display:flex;gap:8px">
          ${editBtn}
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

// ---------- 在线编辑 ----------
async function editItem(path) {
  let content = "";
  try {
    const data = await api("/api/fs/read?path=" + encodeURIComponent(path));
    content = data.content || "";
  } catch (e) { toast(e.message, "err"); return; }
  showModal(`
    <div class="modal" style="max-width:720px">
      <div class="modal-head"><h3 style="word-break:break-all">编辑：${esc(path.split("/").pop())}</h3><button class="modal-close" onclick="closeModal()">×</button></div>
      <div class="modal-body">
        <textarea class="input" id="edit-area" style="height:52vh;font-family:ui-monospace,Consolas,monospace;font-size:13px;white-space:pre;overflow:auto" spellcheck="false"></textarea>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="closeModal()">取消</button>
        <button class="btn primary" onclick="saveEdit('${esc(path)}')">保存</button>
      </div>
    </div>`);
  document.getElementById("edit-area").value = content;
}

async function saveEdit(path) {
  const content = document.getElementById("edit-area").value;
  try {
    await api("/api/fs/edit", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, content }),
    });
    closeModal(); toast("已保存", "ok"); loadFiles(STATE.path);
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 共享文件夹（外部挂载） ----------
const MOUNT = { list: [], id: null, path: "" };

async function loadMountsRoot() {
  MOUNT.id = null; MOUNT.path = "";
  document.getElementById("mount-root").style.display = "";
  document.getElementById("mount-folder").style.display = "none";
  document.getElementById("mount-crumbs").innerHTML = '<span class="cur">共享文件夹</span>';
  let items = [];
  try { items = (await api("/api/mounts")).items; } catch (e) { toast(e.message, "err"); }
  const body = document.getElementById("mount-list-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="3"><div class="empty" style="padding:40px">暂无共享文件夹<br><span style="font-size:12px">管理员可在管理面板「共享文件夹」中添加本机任意目录供大家浏览下载</span></div></td></tr>';
    return;
  }
  body.innerHTML = items.map((m) => `
    <tr>
      <td><div style="display:flex;align-items:center;gap:8px">
        <span class="ico ico-folder"><svg width="30" height="30" viewBox="0 0 24 24" fill="currentColor"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg></span>
        <b>${esc(m.name)}</b></div></td>
      <td style="color:var(--text-2)">${m.readonly ? "只读（可浏览 / 下载）" : "可读写"}</td>
      <td><button class="btn sm primary" onclick="openMount('${m.id}')">打开</button></td>
    </tr>`).join("");
}

async function openMount(id) {
  MOUNT.id = id; MOUNT.path = "";
  document.getElementById("mount-root").style.display = "none";
  document.getElementById("mount-folder").style.display = "";
  const m = (await api("/api/mounts")).items.find((x) => x.id === id);
  document.getElementById("mount-crumbs").innerHTML =
    `<a href="#" onclick="return loadMountsRoot()">共享文件夹</a><span class="sep">/</span><span class="cur">${esc(m ? m.name : id)}</span>`;
  loadMountDir("");
}

async function loadMountDir(rel) {
  MOUNT.path = rel;
  try {
    const data = await api(`/api/mounts/${MOUNT.id}/browse?path=` + encodeURIComponent(rel));
    const body = document.getElementById("mount-files-body");
    if (!data.items.length) {
      body.innerHTML = '<tr><td colspan="4"><div class="empty" style="padding:40px">此文件夹是空的</div></td></tr>';
      return;
    }
    body.innerHTML = data.items.map((it) => {
      const p = encodeURIComponent(it.path);
      return `<tr>
        <td><div style="display:flex;align-items:center;gap:8px;cursor:pointer" ${it.is_dir ? `onclick="loadMountDir('${it.path}')"` : ""}>
          ${it.is_dir ? '<span class="ico ico-folder"><svg width="30" height="30" viewBox="0 0 24 24" fill="currentColor"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg></span>'
            : fileIcon(it.name, false, it.size)}
          <span>${esc(it.name)}</span></div></td>
        <td>${it.is_dir ? "—" : fmtSize(it.size)}</td>
        <td>${fmtTime(it.mtime)}</td>
        <td>${it.is_dir ? '<button class="btn sm" onclick="loadMountDir(\'' + it.path + '\')">打开</button>'
          : '<a class="btn sm" href="/api/mounts/' + MOUNT.id + '/download?path=' + p + '">下载</a>'}</td>
      </tr>`;
    }).join("");
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 分享管理 ----------
async function loadShares() {
  let items = [];
  try { items = (await api("/api/share/list")).items; } catch (e) {}
  const body = document.getElementById("shares-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="6"><div class="empty">还没有分享，回到「我的网盘」选择文件点击分享试试</div></td></tr>';
    return;
  }
  body.innerHTML = items.map((s) => {
    const limit = (s.require_login ? "需登录" : "免登录") +
                  (s.expire_at ? " · " + fmtTime(s.expire_at) + " 过期" : " · 永久");
    return `
    <tr>
      <td>${esc(s.path.split("/").pop() || s.path)}</td>
      <td style="color:var(--text-2)">${esc(s.path || "/")}</td>
      <td style="color:var(--text-2)">${fmtTime(s.created)}</td>
      <td style="color:var(--text-2)">${limit}</td>
      <td><a href="#" onclick="copyLink('${s.token}');return false" style="color:var(--primary)">复制链接</a></td>
      <td><div class="row-actions">
        <button class="btn sm danger" onclick="deleteShare('${s.token}')">取消分享</button>
      </div></td>
    </tr>`;
  }).join("");
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
