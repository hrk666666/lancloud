/* ============================================================
   LanCloud 分享页逻辑（支持强制登录）
   ============================================================ */
"use strict";

const TOKEN = location.pathname.split("/").pop().split("?")[0] || "";

function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function fmtSize(n) {
  if (n < 1024) return n + " B";
  const u = ["KB", "MB", "GB", "TB"];
  let v = n;
  for (const k of u) { v /= 1024; if (v < 1024) return v.toFixed(v < 10 ? 1 : 0) + " " + k; }
  return v.toFixed(1) + " PB";
}
function fmtTime(ts) {
  const d = new Date(ts * 1000);
  const p = (x) => String(x).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
}

const DL = "/api/s/" + TOKEN + "/download?path=";
let CUR = "";   // 当前子目录（相对分享根）

async function api(url, opts) {
  const resp = await fetch(url, opts);
  let data = null;
  try { data = await resp.json(); } catch (e) {}
  if (!resp.ok) throw new Error((data && data.detail) || "加载失败");
  return data;
}

async function doShareLogin(e) {
  e.preventDefault();
  try {
    await api("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("sl-user").value.trim(),
        password: document.getElementById("sl-pass").value,
      }),
    });
    document.getElementById("share-login-card").style.display = "none";
    load();
  } catch (err) {
    alert(err.message);
  }
  return false;
}

function renderSingle(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  const img = ["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"];
  const vid = ["mp4", "webm", "mov", "m4v"];
  const aud = ["mp3", "wav", "ogg", "m4a", "flac"];
  const preview = document.getElementById("single-preview");
  if (img.includes(ext)) preview.innerHTML = `<div class="preview-media" style="margin-top:10px"><img src="${DL}${encodeURIComponent(CUR)}&inline=1" alt="" style="max-height:46vh"></div>`;
  else if (vid.includes(ext)) preview.innerHTML = `<div class="preview-media" style="margin-top:10px"><video controls src="${DL}${encodeURIComponent(CUR)}&inline=1" style="max-width:100%"></video></div>`;
  else if (aud.includes(ext)) preview.innerHTML = `<div class="preview-media" style="margin-top:10px"><audio controls src="${DL}${encodeURIComponent(CUR)}&inline=1"></audio></div>`;
  document.getElementById("single-dl").href = DL + encodeURIComponent(CUR);
}

async function load() {
  try {
    const info = await api("/api/s/" + TOKEN + "/info");
    document.getElementById("sh-title").textContent = info.name;
    document.getElementById("sh-sub").textContent = (info.is_dir ? "文件夹分享 · " : "文件分享 · ") + "仅限同一局域网访问";
    if (info.is_dir) {
      document.getElementById("share-folder").style.display = "";
      await loadDir("");
    } else {
      document.getElementById("share-single").style.display = "";
      document.getElementById("single-name").textContent = info.name;
      document.getElementById("single-icon").innerHTML = folderIcon(false);
      renderSingle(info.name);
    }
  } catch (e) {
    if (e.message.includes("登录")) {
      document.getElementById("sh-title").textContent = "需要登录";
      document.getElementById("share-login-card").style.display = "";
      return;
    }
    document.getElementById("share-empty").style.display = "";
    document.getElementById("sh-title").textContent = "分享不可用";
  }
}

function folderIcon(isDir) {
  if (isDir) return '<span class="ico ico-folder"><svg width="46" height="46" viewBox="0 0 24 24" fill="currentColor"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg></span>';
  return '<span class="ico-type cyan">FILE</span>';
}

async function loadDir(rel) {
  CUR = rel;
  const parts = rel ? rel.split("/") : [];
  let crumb = '<a href="#" onclick="return goDir(\'\')" style="color:var(--primary)">根目录</a>';
  let acc = "";
  parts.forEach((p, i) => {
    acc = acc ? acc + "/" + p : p;
    crumb += ' <span style="color:var(--text-2)">/</span> ' +
      (i === parts.length - 1 ? "<b>" + esc(p) + "</b>" :
        '<a href="#" onclick="return goDir(\'' + acc + '\')" style="color:var(--primary)">' + esc(p) + "</a>");
  });
  document.getElementById("share-crumb").innerHTML = crumb;
  const data = await api("/api/s/" + TOKEN + "/list?path=" + encodeURIComponent(rel));
  const body = document.getElementById("share-items");
  if (!data.items || !data.items.length) {
    body.innerHTML = '<tr><td colspan="4"><div class="empty" style="padding:24px">此文件夹是空的</div></td></tr>';
    return;
  }
  body.innerHTML = data.items.map((it) => {
    const sp = encodeURIComponent(it.share_path || "");
    return `<tr>
      <td><div style="display:flex;align-items:center;gap:8px">${folderIcon(it.is_dir)}<span style="cursor:pointer" ${it.is_dir ? `onclick="goDir('${sp}')"` : ""}>${esc(it.name)}</span></div></td>
      <td style="color:var(--text-2)">${it.is_dir ? "—" : fmtSize(it.size)}</td>
      <td style="color:var(--text-2)">${fmtTime(it.mtime)}</td>
      <td>${it.is_dir ? '<button class="btn sm" onclick="goDir(\'' + sp + '\')">打开</button>'
        : '<a class="btn sm" href="' + DL + sp + '">下载</a>'}</td>
    </tr>`;
  }).join("");
}

function goDir(rel) {
  loadDir(rel);
  return false;
}

load();
