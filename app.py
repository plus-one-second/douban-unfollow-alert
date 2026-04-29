#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import errno
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.douban_unfollow_alert import (
    people_to_state_payload,
    diff_unfollowers,
    fetch_followers,
    load_state,
    resolve_state_path,
    save_state,
    validate_snapshot,
)


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
HOST = "127.0.0.1"
PORT = 8765

jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()


def pending_state_path(state_path: Path) -> Path:
    return state_path.with_name(f"{state_path.stem}.pending{state_path.suffix}")


def history_path(state_path: Path) -> Path:
    return state_path.with_name("history.json")


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>豆瓣取关检测</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f4;
      --ink: #1f2a24;
      --muted: #617067;
      --line: #d9ded6;
      --panel: #ffffff;
      --green: #0a7a35;
      --green-dark: #075829;
      --amber: #9a5a00;
      --red: #b42318;
      --blue: #245ca8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      width: min(920px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 32px 0;
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 18px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }
    h1 {
      margin: 0;
      font-size: 28px;
      font-weight: 760;
      letter-spacing: 0;
    }
    .status-pill {
      min-width: 104px;
      text-align: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 12px;
      color: var(--muted);
      background: #fbfcfa;
    }
    .toolbar {
      display: grid;
      grid-template-columns: minmax(240px, 1fr) auto auto;
      gap: 10px;
      align-items: center;
      margin-top: 22px;
    }
    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    input {
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 11px;
      font: inherit;
      color: var(--ink);
      background: var(--panel);
      outline: none;
    }
    textarea {
      width: 100%;
      min-height: 120px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 11px;
      font: inherit;
      color: var(--ink);
      background: var(--panel);
      outline: none;
    }
    input:focus, textarea:focus { border-color: var(--green); box-shadow: 0 0 0 3px rgba(10, 122, 53, .12); }
    button {
      min-height: 42px;
      border: 1px solid transparent;
      border-radius: 8px;
      padding: 0 15px;
      font: inherit;
      font-weight: 680;
      color: #fff;
      background: var(--green);
      cursor: pointer;
      white-space: nowrap;
    }
    button.secondary {
      color: var(--green-dark);
      border-color: #b8d8c1;
      background: #eef8f1;
    }
    button:disabled {
      cursor: wait;
      opacity: .58;
    }
    section {
      margin-top: 22px;
      padding: 18px 0 0;
    }
    .progress-wrap {
      display: grid;
      gap: 8px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    progress {
      width: 100%;
      height: 14px;
      accent-color: var(--green);
    }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .result {
      border-top: 1px solid var(--line);
      padding-top: 18px;
    }
    .count {
      font-size: 34px;
      font-weight: 780;
      line-height: 1.1;
    }
    .message { color: var(--muted); margin-top: 6px; }
    .setup {
      display: none;
      gap: 14px;
      margin-top: 22px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .setup.is-visible { display: grid; }
    .app-view.is-hidden { display: none; }
    .field-grid {
      display: grid;
      grid-template-columns: minmax(180px, 260px) 1fr;
      gap: 12px;
      align-items: start;
    }
    .help {
      color: var(--muted);
      font-size: 13px;
    }
    details {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      background: #fbfcfa;
    }
    summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--green-dark);
    }
    ol {
      margin: 10px 0 0;
      padding-left: 20px;
      color: var(--muted);
    }
    details ol li {
      display: list-item;
      padding: 8px 0;
      text-align: left;
      border-top: 1px solid var(--line);
    }
    details ol li:first-child { border-top: 0; }
    code {
      padding: 1px 4px;
      border-radius: 4px;
      background: #edf1ed;
      color: var(--ink);
    }
    .account {
      display: flex;
      align-items: center;
      justify-content: flex-start;
      gap: 12px;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 12px;
      background: var(--panel);
    }
    .account-id {
      overflow-wrap: anywhere;
      font-weight: 700;
    }
    .error { color: var(--red); }
    .warning { color: var(--amber); }
    .confirm-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-top: 14px;
    }
    .history-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .history-list {
      display: grid;
      gap: 10px;
    }
    .history-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--panel);
    }
    .history-title {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 8px;
      font-weight: 700;
    }
    ul {
      list-style: none;
      margin: 14px 0 0;
      padding: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: var(--panel);
    }
    li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-top: 1px solid var(--line);
    }
    li:first-child { border-top: 0; }
    a { color: var(--blue); text-decoration: none; }
    a:hover { text-decoration: underline; }
    @media (max-width: 720px) {
      header, .toolbar, .field-grid { grid-template-columns: 1fr; display: grid; align-items: stretch; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>豆瓣取关检测</h1>
        <div class="message">配置保存在本地 config.json</div>
      </div>
      <div id="status" class="status-pill">待检测</div>
    </header>

    <section id="setupView" class="setup">
      <div>
        <div class="count">首次配置</div>
        <div class="message">填写豆瓣 ID 和浏览器 Cookie，保存后会在这个文件夹里自动生成 config.json</div>
      </div>
      <div class="field-grid">
        <label>
          豆瓣 ID
          <input id="setupDoubanId" autocomplete="off" placeholder="例如 152645594">
        </label>
      </div>
      <label>
        Cookie
        <textarea id="setupCookie" spellcheck="false" placeholder="粘贴 Cookie 后面的整串内容"></textarea>
      </label>
      <div class="help">Cookie 等同于临时登录凭证，只会保存在你自己电脑的 config.json 里</div>
      <div id="setupCookieGuide"></div>
      <div class="confirm-row">
        <button id="saveConfigBtn" type="button">保存配置</button>
      </div>
      <div id="setupResult"></div>
    </section>

    <div id="appView" class="app-view">
      <div class="toolbar">
        <div>
          <div class="message">当前检测账号</div>
          <div id="accountView" class="account">
            <span id="accountId" class="account-id">正在读取 config.json...</span>
          </div>
        </div>
        <button id="initBtn" class="secondary">检测人数并设为基线</button>
        <button id="checkBtn">检测是否有人取关</button>
      </div>

      <section class="progress-wrap">
        <progress id="bar" max="100" value="0"></progress>
        <div id="progressText" class="meta">
          <span>还没有开始</span>
        </div>
      </section>

      <section id="result" class="result"></section>

      <section class="result">
        <div class="history-head">
          <div>
            <div class="count">检测历史</div>
            <div class="message">只保存在本地，不包含 Cookie</div>
          </div>
          <button id="refreshHistoryBtn" class="secondary" type="button">刷新历史</button>
        </div>
        <div id="historyList" class="history-list"></div>
      </section>
    </div>
  </main>

  <script>
    const setupView = document.querySelector("#setupView");
    const appView = document.querySelector("#appView");
    const setupDoubanId = document.querySelector("#setupDoubanId");
    const setupCookie = document.querySelector("#setupCookie");
    const saveConfigBtn = document.querySelector("#saveConfigBtn");
    const setupResult = document.querySelector("#setupResult");
    const setupCookieGuide = document.querySelector("#setupCookieGuide");
    const accountId = document.querySelector("#accountId");
    const initBtn = document.querySelector("#initBtn");
    const checkBtn = document.querySelector("#checkBtn");
    const statusEl = document.querySelector("#status");
    const bar = document.querySelector("#bar");
    const progressText = document.querySelector("#progressText");
    const result = document.querySelector("#result");
    const refreshHistoryBtn = document.querySelector("#refreshHistoryBtn");
    const historyList = document.querySelector("#historyList");
    let polling = null;
    let currentDoubanId = "";
    const authErrorNeedles = ["登录或验证页面", "重新登录豆瓣", "Cookie"];
    const cookieGuideHtml = `
      <details>
        <summary>如何复制 Cookie</summary>
        <ol>
          <li>在浏览器里打开豆瓣，确认已经登录</li>
          <li>打开你的豆瓣“关注我的人”页面</li>
          <li>打开开发者工具：Mac 按 <code>Option + Command + I</code>；Windows 按 <code>F12</code> 或 <code>Ctrl + Shift + I</code></li>
          <li>点击顶部的 <code>网络</code></li>
          <li>刷新页面</li>
          <li>在请求列表里点击第一行类似 <code>rlist</code> 或豆瓣页面主请求的项目</li>
          <li>右侧点击 <code>标头</code>，找到 <code>请求标头</code> 里的 <code>Cookie</code></li>
          <li>复制 <code>Cookie</code> 后面的整串内容</li>
        </ol>
      </details>
    `;

    setupCookieGuide.innerHTML = cookieGuideHtml;

    async function loadDefaults() {
      const res = await fetch("/api/config");
      const data = await res.json();
      currentDoubanId = data.douban_user_id || "";
      if (!data.has_config || !data.has_cookie || !currentDoubanId) {
        showSetup(data);
        return;
      }
      showApp();
      renderAccount();
      loadHistory();
    }

    function showSetup(data) {
      setupView.classList.add("is-visible");
      appView.classList.add("is-hidden");
      statusEl.textContent = "需配置";
      setupDoubanId.value = data.douban_user_id || "";
      initBtn.disabled = true;
      checkBtn.disabled = true;
    }

    function showCookieRefresh() {
      showSetup({douban_user_id: currentDoubanId});
      setupCookie.focus();
      setupResult.innerHTML = '<div class="warning">请粘贴新的 Cookie 后保存配置</div>';
    }

    function showApp() {
      setupView.classList.remove("is-visible");
      appView.classList.remove("is-hidden");
      statusEl.textContent = "待检测";
    }

    function renderAccount() {
      accountId.textContent = currentDoubanId || "config.json 里还没有豆瓣 ID";
      initBtn.disabled = !currentDoubanId;
      checkBtn.disabled = !currentDoubanId;
    }

    function setBusy(busy) {
      initBtn.disabled = busy || !currentDoubanId;
      checkBtn.disabled = busy || !currentDoubanId;
      statusEl.textContent = busy ? "检测中" : "待检测";
    }

    async function startJob(mode) {
      if (!currentDoubanId) {
        result.innerHTML = '<div class="error">config.json 里还没有豆瓣 ID，请先在配置文件里填写 douban_user_id</div>';
        return;
      }
      setBusy(true);
      result.innerHTML = "";
      bar.removeAttribute("value");
      progressText.innerHTML = "<span>正在连接豆瓣...</span>";
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode})
      });
      const data = await res.json();
      if (!res.ok) {
        setBusy(false);
        result.innerHTML = `<div class="error">${escapeHtml(data.error || "启动失败")}</div>`;
        return;
      }
      if (polling) clearInterval(polling);
      polling = setInterval(() => pollJob(data.job_id), 900);
      pollJob(data.job_id);
    }

    async function pollJob(jobId) {
      const res = await fetch(`/api/jobs/${jobId}`);
      const job = await res.json();
      renderProgress(job);
      if (job.status === "done" || job.status === "error") {
        clearInterval(polling);
        polling = null;
        setBusy(false);
        renderResult(job);
        loadHistory();
      }
    }

    function renderProgress(job) {
      const p = job.progress || {};
      if (p.expected_total && p.total !== undefined) {
        bar.max = p.expected_total;
        bar.value = Math.min(p.total, p.expected_total);
      } else if (job.status === "done") {
        bar.max = 100;
        bar.value = 100;
      } else {
        bar.removeAttribute("value");
      }
      const bits = [];
      if (p.page) bits.push(`第 ${p.page} 页`);
      if (p.total !== undefined) bits.push(`已识别 ${p.total} 人`);
      if (p.expected_total) bits.push(`页面显示共 ${p.expected_total} 人`);
      if (!bits.length) bits.push(job.status === "queued" ? "等待开始..." : "正在处理...");
      progressText.innerHTML = bits.map(x => `<span>${escapeHtml(x)}</span>`).join("");
    }

    function renderResult(job) {
      statusEl.textContent = job.status === "done" ? "完成" : "出错";
      if (job.status === "error") {
        result.innerHTML = renderError(job.error || "检测失败");
        const refreshBtn = document.querySelector("#refreshCookieBtn");
        if (refreshBtn) refreshBtn.addEventListener("click", showCookieRefresh);
        return;
      }
      const r = job.result;
      const title = job.mode === "init" ? "基线已更新" : "检测完成";
      const unfollowers = r.unfollowers || [];
      let html = `<div class="count">${r.current_count}</div>`;
      html += `<div class="message">${title}，当前关注者人数为 ${r.current_count}</div>`;
      if (job.mode === "check") {
        if (unfollowers.length === 0) {
          html += '<div class="message">没有发现取关</div>';
        } else {
          html += `<div class="warning">发现 ${unfollowers.length} 个可能取关的人：</div>`;
          html += `<div class="message">基线还没有更新。确认结果没问题后，再点击下面的按钮保存这次名单。</div>`;
          html += `<div class="confirm-row"><button id="confirmBaselineBtn" type="button">确认并更新基线</button></div>`;
          html += "<ul>" + unfollowers.map(person => (
            `<li><span>${escapeHtml(person.name)}</span><a target="_blank" rel="noreferrer" href="${person.url}">打开主页</a></li>`
          )).join("") + "</ul>";
        }
      }
      result.innerHTML = html;
      const confirmBtn = document.querySelector("#confirmBaselineBtn");
      if (confirmBtn) {
        confirmBtn.addEventListener("click", () => confirmBaseline(job.job_id, confirmBtn));
      }
    }

    function isAuthError(message) {
      return authErrorNeedles.some(needle => String(message).includes(needle));
    }

    function renderError(message) {
      const safe = escapeHtml(message);
      if (!isAuthError(message)) return `<div class="error">${safe}</div>`;
      return `
        <div class="error">${safe}</div>
        <div class="confirm-row">
          <button id="refreshCookieBtn" type="button">重新配置 Cookie</button>
        </div>
        ${cookieGuideHtml}
      `;
    }

    async function confirmBaseline(jobId, button) {
      button.disabled = true;
      button.textContent = "正在保存...";
      const res = await fetch(`/api/jobs/${jobId}/confirm`, {method: "POST"});
      const data = await res.json();
      if (!res.ok) {
        button.disabled = false;
        button.textContent = "确认并更新基线";
        result.insertAdjacentHTML("beforeend", `<div class="error">${escapeHtml(data.error || "保存失败")}</div>`);
        return;
      }
      button.textContent = "基线已更新";
      result.insertAdjacentHTML("beforeend", '<div class="message">已把这次名单保存为新的基线</div>');
      loadHistory();
    }

    async function loadHistory() {
      const res = await fetch("/api/history");
      const data = await res.json();
      if (!res.ok) {
        historyList.innerHTML = `<div class="error">${escapeHtml(data.error || "读取历史失败")}</div>`;
        return;
      }
      const entries = data.history || [];
      if (!entries.length) {
        historyList.innerHTML = '<div class="message">还没有检测历史</div>';
        return;
      }
      historyList.innerHTML = entries.map(renderHistoryItem).join("");
    }

    function renderHistoryItem(entry) {
      const time = formatTime(entry.checked_at);
      const mode = entry.mode === "init" ? "建立基线" : "检测取关";
      const previous = entry.previous_count === null || entry.previous_count === undefined ? "无" : entry.previous_count;
      const delta = entry.delta === null || entry.delta === undefined ? "" : `，变化 ${entry.delta > 0 ? "+" : ""}${entry.delta}`;
      const unfollowers = entry.unfollowers || [];
      const baseline = entry.baseline_saved ? "已更新基线" : "待确认更新基线";
      let html = `<div class="history-item">`;
      html += `<div class="history-title"><span>${escapeHtml(mode)} · ${escapeHtml(time)}</span><span>${escapeHtml(baseline)}</span></div>`;
      html += `<div class="message">上次 ${previous} 人，本次 ${entry.current_count} 人${delta}</div>`;
      if (unfollowers.length) {
        html += `<div class="warning">发现 ${unfollowers.length} 个可能取关的人：</div>`;
        html += "<ul>" + unfollowers.map(person => (
          `<li><span>${escapeHtml(person.name)}</span><a target="_blank" rel="noreferrer" href="${person.url}">打开主页</a></li>`
        )).join("") + "</ul>";
      }
      html += `</div>`;
      return html;
    }

    function formatTime(value) {
      if (!value) return "未知时间";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.toLocaleString();
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    initBtn.addEventListener("click", () => startJob("init"));
    checkBtn.addEventListener("click", () => startJob("check"));
    refreshHistoryBtn.addEventListener("click", loadHistory);
    saveConfigBtn.addEventListener("click", async () => {
      const douban_user_id = setupDoubanId.value.trim();
      const cookie = setupCookie.value.trim();
      setupResult.innerHTML = "";
      if (!douban_user_id || !cookie) {
        setupResult.innerHTML = '<div class="error">请填写豆瓣 ID 和 Cookie</div>';
        return;
      }
      saveConfigBtn.disabled = true;
      saveConfigBtn.textContent = "正在保存...";
      const res = await fetch("/api/config", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({douban_user_id, cookie})
      });
      const data = await res.json();
      saveConfigBtn.disabled = false;
      saveConfigBtn.textContent = "保存配置";
      if (!res.ok) {
        setupResult.innerHTML = `<div class="error">${escapeHtml(data.error || "保存失败")}</div>`;
        return;
      }
      currentDoubanId = data.douban_user_id || douban_user_id;
      setupCookie.value = "";
      showApp();
      renderAccount();
      result.innerHTML = '<div class="message">配置已保存，现在可以检测人数并设为基线</div>';
    });
    loadDefaults();
  </script>
</body>
</html>
"""


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    size = int(handler.headers.get("Content-Length", "0"))
    if size <= 0:
        return {}
    return json.loads(handler.rfile.read(size).decode("utf-8"))


def read_config_file() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_config_file(douban_user_id: str, cookie: str) -> dict[str, Any]:
    config = read_config_file()
    config.update(
        {
            "douban_user_id": douban_user_id,
            "cookie": cookie,
            "state_file": config.get("state_file", ".state/followers.json"),
            "request_delay_seconds": config.get("request_delay_seconds", 1.5),
            "max_pages": config.get("max_pages", 80),
            "notify": config.get(
                "notify",
                {
                    "terminal": True,
                    "macos": True,
                    "webhook_url": "",
                },
            ),
        }
    )
    tmp = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(CONFIG_PATH)
    return config


def load_app_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise RuntimeError("找不到 config.json，请先在首次配置页面填写豆瓣 ID 和 Cookie")
    config = read_config_file()
    if not config.get("cookie"):
        raise RuntimeError("config.json 里缺少 cookie")
    if not config.get("douban_user_id"):
        raise RuntimeError("config.json 里缺少豆瓣 ID")
    return config


def serialize_people(people: list[Any]) -> list[dict[str, str]]:
    return [{"user_id": p.user_id, "name": p.name, "url": p.url} for p in people]


def write_pending_state(path: Path, current: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(people_to_state_payload(current), fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def read_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return payload
    return []


def write_history(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(entries[:200], fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def append_history(path: Path, entry: dict[str, Any]) -> None:
    entries = read_history(path)
    write_history(path, [entry] + entries)


def mark_history_confirmed(path: Path, entry_id: str) -> None:
    entries = read_history(path)
    for entry in entries:
        if entry.get("id") == entry_id:
            entry["baseline_saved"] = True
            entry["confirmed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            break
    write_history(path, entries)


def update_job(job_id: str, **updates: Any) -> None:
    with jobs_lock:
        jobs[job_id].update(updates)


def run_job(job_id: str, mode: str) -> None:
    try:
        update_job(job_id, status="running", started_at=time.time())
        config = load_app_config()
        state_path = resolve_state_path(CONFIG_PATH, config)
        hist_path = history_path(state_path)
        previous = load_state(state_path)

        def on_progress(progress: dict[str, Any]) -> None:
            update_job(job_id, progress=progress)

        current = fetch_followers(config, progress=on_progress)
        validate_snapshot(previous, current, allow_shrink=(mode == "init"))
        unfollowers = [] if mode == "init" else diff_unfollowers(previous, current)
        previous_count = len(previous.get("followers", {})) if previous else None
        pending_path = pending_state_path(state_path)
        baseline_saved = mode == "init" or not unfollowers
        if baseline_saved:
            save_state(state_path, current)
            if pending_path.exists():
                pending_path.unlink()
        else:
            write_pending_state(pending_path, current)
        history_entry = {
            "id": job_id,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": mode,
            "previous_count": previous_count,
            "current_count": len(current),
            "delta": None if previous_count is None else len(current) - previous_count,
            "unfollowers": serialize_people(unfollowers),
            "baseline_saved": baseline_saved,
        }
        append_history(hist_path, history_entry)
        update_job(
            job_id,
            status="done",
            finished_at=time.time(),
            result={
                "current_count": len(current),
                "unfollowers": serialize_people(unfollowers),
                "state_file": str(state_path),
                "pending_state_file": str(pending_path),
                "history_file": str(hist_path),
                "baseline_saved": baseline_saved,
            },
        )
    except Exception as exc:
        update_job(job_id, status="error", error=str(exc), finished_at=time.time())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/config":
            try:
                loaded = read_config_file()
                self.send_json(
                    {
                        "has_config": CONFIG_PATH.exists(),
                        "has_cookie": bool(loaded.get("cookie")),
                        "douban_user_id": loaded.get("douban_user_id", ""),
                    }
                )
            except json.JSONDecodeError:
                self.send_json(
                    {
                        "has_config": True,
                        "has_cookie": False,
                        "douban_user_id": "",
                        "error": "config.json 格式不正确",
                    }
                )
            return
        if path == "/api/history":
            self.get_history()
            return
        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            with jobs_lock:
                job = jobs.get(job_id)
            if not job:
                self.send_json({"error": "任务不存在"}, status=404)
                return
            self.send_json(job)
            return
        self.send_json({"error": "Not found"}, status=404)

    def get_history(self) -> None:
        try:
            config = load_app_config()
            state_path = resolve_state_path(CONFIG_PATH, config)
            self.send_json({"history": read_history(history_path(state_path))})
        except Exception as exc:
            self.send_json({"error": str(exc), "history": []}, status=400)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/config":
            self.save_config()
            return
        if path != "/api/jobs":
            if path.startswith("/api/jobs/") and path.endswith("/confirm"):
                job_id = path.split("/")[-2]
                self.confirm_job(job_id)
                return
            self.send_json({"error": "Not found"}, status=404)
            return
        try:
            payload = read_json_body(self)
            mode = payload.get("mode")
            if mode not in {"init", "check"}:
                raise ValueError("未知检测模式")
            job_id = uuid.uuid4().hex
            with jobs_lock:
                jobs[job_id] = {
                    "job_id": job_id,
                    "mode": mode,
                    "status": "queued",
                    "progress": {},
                    "created_at": time.time(),
                }
            thread = threading.Thread(target=run_job, args=(job_id, mode), daemon=True)
            thread.start()
            self.send_json({"job_id": job_id})
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def save_config(self) -> None:
        try:
            payload = read_json_body(self)
            douban_user_id = str(payload.get("douban_user_id", "")).strip().strip("/")
            cookie = str(payload.get("cookie", "")).strip()
            if not douban_user_id:
                raise ValueError("请填写豆瓣 ID")
            if not cookie:
                raise ValueError("请粘贴 Cookie")
            if cookie.lower().startswith("cookie:"):
                cookie = cookie.split(":", 1)[1].strip()
            config = write_config_file(douban_user_id, cookie)
            self.send_json(
                {
                    "ok": True,
                    "has_config": True,
                    "has_cookie": True,
                    "douban_user_id": config.get("douban_user_id", ""),
                }
            )
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def confirm_job(self, job_id: str) -> None:
        with jobs_lock:
            job = jobs.get(job_id)
        if not job or job.get("status") != "done":
            self.send_json({"error": "找不到可确认的检测结果"}, status=404)
            return
        result = job.get("result") or {}
        pending = result.get("pending_state_file")
        state = result.get("state_file")
        hist = result.get("history_file")
        if not pending or not state:
            self.send_json({"error": "没有待保存的基线"}, status=400)
            return
        pending_path = Path(pending)
        state_path = Path(state)
        if not pending_path.exists():
            self.send_json({"error": "待确认名单不存在，可能已经保存过了"}, status=400)
            return
        state_path.parent.mkdir(parents=True, exist_ok=True)
        pending_path.replace(state_path)
        if hist:
            mark_history_confirmed(Path(hist), job_id)
        result["baseline_saved"] = True
        with jobs_lock:
            job["result"] = result
        self.send_json({"ok": True})


def main() -> None:
    server = None
    port = PORT
    for candidate in range(PORT, PORT + 20):
        try:
            server = ThreadingHTTPServer((HOST, candidate), Handler)
            port = candidate
            break
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
    if server is None:
        raise RuntimeError("找不到可用的本地端口，请关闭已经打开的检测器窗口后再试")
    url = f"http://{HOST}:{port}/"
    print(f"Douban Unfollow Alert is running at {url}")
    if os.environ.get("DOUBAN_APP_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
