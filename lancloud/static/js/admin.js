/* ============================================================
   LanCloud 管理面板逻辑
   ============================================================ */
"use strict";

function toast(msg, type) {
  const box = document.getElementById("toast-box");
  const el = document.createElement("div");
  el.className = "toast" + (type ? " " + type : "");
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), type === "err" ? 4000 : 2600);
}

function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmtSize(n) {
  if (!n && n !== 0) return "-";
  if (n < 1024) return n + " B";
  const units = ["KB", "MB", "GB", "TB"];
  let v = n;
  for (const u of units) { v /= 1024; if (v < 1024) return v.toFixed(v < 10 ? 1 : 0) + " " + u; }
  return v.toFixed(1) + " PB";
}

async function api(url, opts) {
  const resp = await fetch(url, opts);
  let data = null;
  try { data = await resp.json(); } catch (e) {}
  if (!resp.ok) throw new Error((data && data.detail) || (data && data.error) || "请求失败");
  return data;
}

function switchTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-pane").forEach((p) =>
    p.classList.toggle("active", p.id === "pane-" + name));
  if (name === "users") loadUsers();
  if (name === "mounts") loadMounts();
  if (name === "https") loadHttpsStatus();
  if (name === "wizard") { loadDnsLog(); }
}

// ---------- 概览 ----------
let OVERVIEW = null;

async function loadOverview() {
  try {
    OVERVIEW = await api("/api/admin/overview");
  } catch (e) {
    location.href = "/";
    return;
  }
  document.getElementById("user-name").textContent = "管理员";
  document.getElementById("st-users").textContent = OVERVIEW.users;
  document.getElementById("st-files").textContent = OVERVIEW.files;
  document.getElementById("st-size").textContent = fmtSize(OVERVIEW.total_size);
  document.getElementById("st-web").textContent = ":" + OVERVIEW.web_port;
  document.getElementById("st-ip").textContent = (OVERVIEW.ips[0] ? "http://" + OVERVIEW.ips[0] + ":" + OVERVIEW.web_port : "未检测到局域网 IP");
  const dnsEl = document.getElementById("st-dns");
  if (OVERVIEW.dns.running) {
    dnsEl.innerHTML = '<span class="badge ok">运行中</span>';
    document.getElementById("st-dns-sub").textContent = "监听 " + OVERVIEW.dns.port + " 端口";
  } else {
    dnsEl.innerHTML = '<span class="badge err">未运行</span>';
    document.getElementById("st-dns-sub").textContent = OVERVIEW.dns.error || "点击下方按钮启动";
  }
  const httpsEl = document.getElementById("st-https");
  if (OVERVIEW.https_enabled) {
    httpsEl.innerHTML = '<span class="badge ok">已启用</span>';
    document.getElementById("st-https-sub").textContent = "端口 " + OVERVIEW.https_port + "（重启后生效）";
  } else {
    httpsEl.innerHTML = '<span class="badge off">未启用</span>';
    document.getElementById("st-https-sub").textContent = "见 HTTPS 标签页";
  }
  document.getElementById("sys-webport").textContent = ":" + OVERVIEW.web_port;
  document.getElementById("sys-dnsport").textContent = ":" + OVERVIEW.dns_port;
  document.getElementById("sys-reg").textContent = OVERVIEW.allow_register ? "开放" : "关闭";
  document.getElementById("sys-reg-now").textContent = OVERVIEW.allow_register ? "当前：开放" : "当前：关闭";
  document.getElementById("sys-quota").value = OVERVIEW.default_quota_mb;
  const tip = document.getElementById("t-ip");
  if (tip && OVERVIEW.ips[0]) tip.textContent = OVERVIEW.ips[0];
  // 向导状态
  const wiz = document.getElementById("wiz-dns-status");
  if (wiz) {
    wiz.innerHTML = OVERVIEW.dns.running
      ? `<span class="badge ok">运行中（端口 ${OVERVIEW.dns.port}）✓</span>`
      : `<span class="badge err">未运行</span> ${esc(OVERVIEW.dns.error || "")}`;
  }
  loadDomains();
}

// ---------- DNS 服务控制 ----------
async function toggleDns(forceStart) {
  try {
    const data = await api("/api/dns/" + (forceStart ? "start" : "stop"), { method: "POST" });
    toast(data.message || (forceStart ? "已启动" : "已停止"), data.ok ? "ok" : "err");
    loadOverview();
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 域名映射 ----------
async function loadDomains() {
  let items = [];
  try { items = (await api("/api/dns/domains")).items; } catch (e) {}
  const body = document.getElementById("domains-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5"><div class="empty" style="padding:20px">还没有域名映射。添加一个试试，例如 <b>pan.lan</b> → 你的 IP。</div></td></tr>';
    return;
  }
  body.innerHTML = items.map((d) => `
    <tr>
      <td><b>${esc(d.domain)}</b></td>
      <td style="color:var(--text-2)">${esc(d.ip)}</td>
      <td><label class="switch"><input type="checkbox" ${d.enabled ? "checked" : ""} onchange="toggleDomain('${d.id}', this.checked)"><i></i></label></td>
      <td style="color:var(--text-2)">${esc(d.note || "")}</td>
      <td><div class="row-actions">
        <button class="btn sm danger" onclick="delDomain('${d.id}')">删除</button>
      </div></td>
    </tr>`).join("");
}

async function addDomain() {
  const domain = document.getElementById("dns-domain").value.trim();
  const ip = document.getElementById("dns-ip").value.trim();
  const note = document.getElementById("dns-note").value.trim();
  if (!domain) { toast("请填写域名", "err"); return; }
  try {
    await api("/api/dns/domains", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, ip, note }),
    });
    toast("映射已添加", "ok");
    document.getElementById("dns-domain").value = "";
    document.getElementById("dns-note").value = "";
    loadDomains();
  } catch (e) { toast(e.message, "err"); }
}

async function toggleDomain(id, enabled) {
  try {
    await api("/api/dns/domains/" + id, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    toast(enabled ? "已启用" : "已停用", "ok");
  } catch (e) { toast(e.message, "err"); loadDomains(); }
}

async function delDomain(id) {
  if (!confirm("确定删除该映射吗？")) return;
  try {
    await api("/api/dns/domains/" + id, { method: "DELETE" });
    toast("已删除", "ok");
    loadDomains();
  } catch (e) { toast(e.message, "err"); }
}

async function fillSelfIp() {
  try {
    const ov = await api("/api/admin/overview");
    if (ov.ips && ov.ips[0]) {
      document.getElementById("dns-ip").value = ov.ips[0];
      toast("已填入 " + ov.ips[0], "ok");
    } else {
      toast("未检测到 IP，请手动填写（如 192.168.1.100）", "err");
    }
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 一键诊断 ----------
async function runDiag() {
  const box = document.getElementById("diag-result");
  box.style.display = "";
  box.innerHTML = '<div class="notice info">正在诊断…</div>';
  let d;
  try { d = await api("/api/diag"); } catch (e) { box.innerHTML = '<div class="notice err">诊断失败：' + esc(e.message) + "</div>"; return; }

  let html = '<div class="card" style="padding:16px;margin-top:4px"><b>一键诊断结果</b><div style="margin-top:8px;display:flex;flex-direction:column;gap:8px">';

  // DNS 状态
  html += '<div>' + (d.dns.running ? '<span class="badge ok">DNS 运行中</span>' : '<span class="badge err">DNS 未运行</span>') +
          "　" + esc(d.dns.error || ("监听端口 " + d.dns.port)) + "</div>";

  // 本机 IP
  html += '<div>本机局域网 IP：' + (d.ips.length ? d.ips.map((i) => "<code>" + esc(i) + "</code>").join("、") : '<span class="badge err">未检测到</span>') + "</div>";

  // 自测
  html += '<div><b>DNS 自测（本机向自己发查询）：</b></div>';
  for (const t of d.self_tests) {
    html += '<div style="padding-left:14px">' +
      (t.domain ? `<code>${esc(t.domain)}</code> 期望 ${esc(t.expect)} → ` : "") +
      (t.ok ? '<span class="badge ok">通过</span>' : '<span class="badge err">失败</span>') +
      "　" + esc(t.detail || "") + "</div>";
  }
  if (d.dns.running && d.domains.length === 0) {
    html += '<div class="notice warn" style="margin:0">没有配置任何域名映射，请先添加（如 pan.lan → 本机 IP）</div>';
  }

  // 防火墙提示
  html += '<div><b>防火墙放行建议（保证其他设备能连上本机）：</b></div>';
  d.firewall_tips.forEach((t) => html += '<div class="code-block" style="margin:2px 0 0 14px">' + esc(t) + "</div>");

  html += "</div></div>";
  box.innerHTML = html;
}

// ---------- DNS 查询日志 ----------
async function loadDnsLog() {
  const box = document.getElementById("dns-log-box");
  if (!box) return;
  let items = [];
  try { items = (await api("/api/dns/log")).items; } catch (e) {}
  if (!items.length) {
    box.innerHTML = "（暂无查询记录——说明还没有设备把 DNS 指到本机，先按向导第 3 步配置）";
    return;
  }
  box.innerHTML = items.slice(0, 30).map(([ts, client, qname, action]) => {
    const d = new Date(ts * 1000);
    const p = (x) => String(x).padStart(2, "0");
    return `<div><code style="color:var(--text-2)">${d.getHours()}:${p(d.getMinutes())}:${p(d.getSeconds())}</code>  <b>${esc(client)}</b> → ${esc(qname)}　${esc(action)}</div>`;
  }).join("") + (items.length > 30 ? `<div style="color:var(--text-2);font-size:12px">…仅显示最近 30 条</div>` : "");
}

// ---------- 用户管理 ----------
function toggleBatchPanel() {
  const el = document.getElementById("batch-panel");
  el.style.display = el.style.display === "none" ? "" : "none";
}

async function loadUsers() {
  let items = [];
  try { items = (await api("/api/admin/users")).items; } catch (e) { toast(e.message, "err"); return; }
  const body = document.getElementById("users-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="7"><div class="empty" style="padding:20px">暂无用户</div></td></tr>';
    return;
  }
  body.innerHTML = items.map((u) => {
    const quotaTxt = u.quota_mb > 0 ? (u.quota_mb >= 1024 ? (u.quota_mb / 1024) + " GB" : u.quota_mb + " MB") : "不限";
    const usedTxt = fmtSize(u.used);
    const isSelf = u.username === OVERVIEW.admin_user;
    return `<tr>
      <td><b>${esc(u.username)}</b>${u.is_admin ? ' <span class="badge blue">管理员</span>' : ""}</td>
      <td>${u.is_admin ? "管理员" : "普通用户"}</td>
      <td style="color:var(--text-2)">${usedTxt} / ${quotaTxt}</td>
      <td>${u.file_count}</td>
      <td><label class="switch"><input type="checkbox" ${u.can_share ? "checked" : ""} onchange="setCanShare('${esc(u.username)}', this.checked)"><i></i></label></td>
      <td>${u.disabled ? '<span class="badge err">已禁用</span>' : '<span class="badge ok">正常</span>'}</td>
      <td><div class="row-actions" style="flex-wrap:wrap">
        <button class="btn sm" onclick="editUser('${esc(u.username)}')">编辑</button>
        ${u.disabled
          ? `<button class="btn sm" onclick="setDisabled('${esc(u.username)}', false)">启用</button>`
          : `<button class="btn sm" onclick="setDisabled('${esc(u.username)}', true)">禁用</button>`}
        ${u.is_admin ? "" : `<button class="btn sm danger" onclick="delUser('${esc(u.username)}')">删除</button>`}
      </div></td>
    </tr>`;
  }).join("");
}

async function createUser() {
  const username = document.getElementById("nu-user").value.trim();
  const password = document.getElementById("nu-pass").value;
  const quotaRaw = document.getElementById("nu-quota").value.trim();
  const quota_mb = quotaRaw ? parseInt(quotaRaw, 10) : undefined;
  if (!username) { toast("请填写用户名", "err"); return; }
  try {
    await api("/api/admin/users", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, quota_mb }),
    });
    toast("账号已创建", "ok");
    document.getElementById("nu-user").value = "";
    document.getElementById("nu-pass").value = "";
    document.getElementById("nu-quota").value = "";
    loadUsers();
  } catch (e) { toast(e.message, "err"); }
}

async function batchCreate() {
  const lines = document.getElementById("batch-text").value;
  if (!lines.trim()) { toast("请填写账号列表", "err"); return; }
  const out = document.getElementById("batch-result");
  out.textContent = "处理中…";
  try {
    const data = await api("/api/admin/users/batch", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines }),
    });
    const ok = data.results.filter((r) => r.ok).length;
    const fail = data.results.filter((r) => !r.ok);
    out.textContent = `成功 ${ok} 个` + (fail.length ? `，失败 ${fail.length} 个：` + fail.map((f) => f.username + "(" + f.error + ")").join("；") : "");
    loadUsers();
  } catch (e) { out.textContent = "失败：" + e.message; }
}

function editUser(username) {
  showAdminModal(`
    <div class="modal" style="max-width:440px">
      <div class="modal-head"><h3>编辑用户：${esc(username)}</h3><button class="modal-close" onclick="closeAdminModal()">×</button></div>
      <div class="modal-body">
        <div class="form-row"><label>存储配额（MB，0 = 不限）</label>
          <input class="input" id="eu-quota" placeholder="例如 1024"></div>
        <div class="form-row"><label>重置密码（留空则不修改）</label>
          <input class="input" id="eu-pass" placeholder="新密码（至少 6 位）"></div>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="closeAdminModal()">取消</button>
        <button class="btn primary" onclick="saveUser('${esc(username)}')">保存</button>
      </div>
    </div>`);
}

async function saveUser(username) {
  const q = document.getElementById("eu-quota").value.trim();
  const p = document.getElementById("eu-pass").value;
  const body = {};
  if (q !== "") body.quota_mb = parseInt(q, 10);
  try {
    if (Object.keys(body).length) {
      await api("/api/admin/users/" + encodeURIComponent(username), {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    }
    if (p) {
      await api("/api/admin/users/" + encodeURIComponent(username) + "/reset-password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: p }),
      });
    }
    closeAdminModal();
    toast("已保存", "ok");
    loadUsers();
  } catch (e) { toast(e.message, "err"); }
}

async function setCanShare(username, val) {
  try {
    await api("/api/admin/users/" + encodeURIComponent(username), {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ can_share: val }),
    });
    toast(val ? "已允许分享" : "已禁止分享", "ok");
  } catch (e) { toast(e.message, "err"); }
}

async function setDisabled(username, val) {
  try {
    await api("/api/admin/users/" + encodeURIComponent(username), {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disabled: val }),
    });
    toast(val ? "已禁用该账号" : "已启用该账号", "ok");
    loadUsers();
  } catch (e) { toast(e.message, "err"); }
}

async function delUser(username) {
  if (!confirm("确定删除用户「" + username + "」吗？\n该用户的全部文件将被永久删除，不可恢复！")) return;
  try {
    await api("/api/admin/users/" + encodeURIComponent(username), { method: "DELETE" });
    toast("用户已删除", "ok");
    loadUsers();
    loadOverview();
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 共享文件夹（挂载） ----------
async function loadMounts() {
  let items = [];
  try { items = (await api("/api/mounts")).items; } catch (e) { toast(e.message, "err"); return; }
  const body = document.getElementById("mounts-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5"><div class="empty" style="padding:20px">还没有共享文件夹。填写本机路径添加一个。</div></td></tr>';
    return;
  }
  body.innerHTML = items.map((m) => `
    <tr>
      <td><b>${esc(m.name)}</b></td>
      <td style="color:var(--text-2);word-break:break-all">${esc(m.path)}</td>
      <td>${m.readonly ? "只读" : "读写"}</td>
      <td><label class="switch"><input type="checkbox" ${m.enabled ? "checked" : ""} onchange="toggleMount('${m.id}', this.checked)"><i></i></label></td>
      <td><div class="row-actions">
        <button class="btn sm" onclick="editMount('${m.id}')">编辑</button>
        <button class="btn sm danger" onclick="delMount('${m.id}')">删除</button>
      </div></td>
    </tr>`).join("");
}

async function addMount() {
  const name = document.getElementById("mt-name").value.trim();
  const path = document.getElementById("mt-path").value.trim();
  if (!name || !path) { toast("请填写共享名称和路径", "err"); return; }
  try {
    await api("/api/mounts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, path, readonly: true }),
    });
    toast("共享已添加", "ok");
    document.getElementById("mt-name").value = "";
    document.getElementById("mt-path").value = "";
    loadMounts();
  } catch (e) { toast(e.message, "err"); }
}

async function editMount(id) {
  let m = null;
  try {
    const items = (await api("/api/mounts")).items;
    m = items.find((x) => x.id === id);
  } catch (e) {}
  showAdminModal(`
    <div class="modal" style="max-width:460px">
      <div class="modal-head"><h3>编辑共享</h3><button class="modal-close" onclick="closeAdminModal()">×</button></div>
      <div class="modal-body">
        <div class="form-row"><label>共享名称</label><input class="input" id="em-name" value="${esc(m ? m.name : "")}"></div>
        <div class="form-row"><label>文件夹路径</label><input class="input" id="em-path" value="${esc(m ? m.path : "")}" placeholder="D:\\Movies 或 /home/user/共享"></div>
        <div class="form-row"><label>权限</label>
          <select class="select" id="em-ro"><option value="1" ${m && !m.readonly ? "" : "selected"}>只读（浏览 / 下载）</option><option value="0" ${m && !m.readonly ? "selected" : ""}>读写</option></select></div>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="closeAdminModal()">取消</button>
        <button class="btn primary" onclick="saveMount('${id}')">保存</button>
      </div>
    </div>`);
}

async function saveMount(id) {
  const name = document.getElementById("em-name").value.trim();
  const path = document.getElementById("em-path").value.trim();
  const readonly = document.getElementById("em-ro").value === "1";
  const body = { name, path, readonly };
  try {
    await api("/api/mounts/" + id, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    closeAdminModal();
    toast("已保存", "ok");
    loadMounts();
  } catch (e) { toast(e.message, "err"); }
}

async function toggleMount(id, val) {
  try {
    await api("/api/mounts/" + id, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: val }),
    });
    toast(val ? "已启用" : "已停用", "ok");
  } catch (e) { toast(e.message, "err"); }
}

async function delMount(id) {
  if (!confirm("确定删除该共享吗？不会删除原文件夹，只是取消共享。")) return;
  try {
    await api("/api/mounts/" + id, { method: "DELETE" });
    toast("已删除共享", "ok");
    loadMounts();
  } catch (e) { toast(e.message, "err"); }
}

// ---------- HTTPS ----------
async function loadHttpsStatus() {
  let s = null;
  try { s = await api("/api/https/status"); } catch (e) { return; }
  document.getElementById("https-status").innerHTML = s.enabled
    ? '<span class="badge ok">已启用</span>' : '<span class="badge off">未启用</span>';
  document.getElementById("https-port-sub").textContent = "端口 " + s.port + " · CA 证书" + (s.ca_ready ? "已生成" : "未生成（下载时自动生成）");
  document.getElementById("https-port").value = s.port;
}

async function setHttps(enabled) {
  const port = parseInt(document.getElementById("https-port").value || "8443", 10);
  try {
    const data = await api("/api/https/set", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, port }),
    });
    toast(data.message || "已保存", "ok");
    loadHttpsStatus();
    loadOverview();
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 系统设置 ----------
async function setRegister(val) {
  await saveSys({ allow_register: val });
}

async function setDefaultQuota() {
  const q = parseInt(document.getElementById("sys-quota").value || "0", 10);
  await saveSys({ default_quota_mb: q });
}

async function saveSys(patch) {
  try {
    await api("/api/admin/config", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    toast("已保存", "ok");
    loadOverview();
  } catch (e) { toast(e.message, "err"); }
}

// ---------- 模态框 ----------
function showAdminModal(html) {
  const root = document.getElementById("modal-root");
  if (!root) {
    const d = document.createElement("div");
    d.id = "modal-root";
    document.body.appendChild(d);
  }
  document.getElementById("modal-root").innerHTML =
    `<div class="modal-mask show" onclick="if(event.target===this)closeAdminModal()">${html}</div>`;
}
function closeAdminModal() {
  const root = document.getElementById("modal-root");
  if (root) root.innerHTML = "";
}

// ---------- 退出 ----------
async function doLogout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) {}
  location.href = "/";
}

loadOverview();
