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
}

// ---------- 概览 ----------
let OVERVIEW = null;

async function loadOverview() {
  try {
    OVERVIEW = await api("/api/admin/overview");
  } catch (e) {
    // 未登录 → 回网盘页登录
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
    document.getElementById("st-dns-sub").textContent = "监听 UDP " + OVERVIEW.dns.port;
  } else {
    dnsEl.innerHTML = '<span class="badge off">未运行</span>';
    document.getElementById("st-dns-sub").textContent = OVERVIEW.dns.error || "点击下方按钮启动";
  }
  document.getElementById("sys-webport").textContent = ":" + OVERVIEW.web_port;
  document.getElementById("sys-dnsport").textContent = ":" + OVERVIEW.dns_port;
  document.getElementById("sys-reg").textContent = OVERVIEW.allow_register ? "开放" : "关闭";
  // 教程页显示 IP
  const tip = document.getElementById("t-ip");
  if (tip && OVERVIEW.ips[0]) tip.textContent = OVERVIEW.ips[0];
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

// ---------- 退出 ----------
async function doLogout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) {}
  location.href = "/";
}

loadOverview();
