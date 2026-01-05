const statusEl = document.getElementById("status");
const summaryEl = document.getElementById("summary");
const jsonEl = document.getElementById("json");
const btnExtract = document.getElementById("btnExtract");
const btnCopy = document.getElementById("btnCopy");
const btnSave = document.getElementById("btnSave");
const pdfFileInput = document.getElementById("pdfFile");
const btnPdf = document.getElementById("btnPdf");
const btnCompare = document.getElementById("btnCompare");
const pdfSummaryEl = document.getElementById("pdfSummary");
const pdfJsonEl = document.getElementById("pdfJson");
const cmpSummaryEl = document.getElementById("cmpSummary");
const cmpJsonEl = document.getElementById("cmpJson");

let lastPayload = null;
let lastPdfPayload = null;

function setStatus(text) {
  statusEl.textContent = text || "";
}

function fmtTime(ts) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return "";
  }
}

function render(payload) {
  lastPayload = payload;
  if (!payload) {
    summaryEl.innerHTML = `<div class="muted">暂无数据</div>`;
    jsonEl.textContent = "";
    btnCopy.disabled = true;
    btnSave.disabled = true;
    return;
  }
  const safeTitle = (payload.title || "").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const safeUrl = (payload.url || "").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const linkCount = Array.isArray(payload.links) ? payload.links.length : 0;
  summaryEl.innerHTML = `
    <div><span class="muted">标题：</span>${safeTitle || "-"}</div>
    <div><span class="muted">地址：</span>${safeUrl || "-"}</div>
    <div><span class="muted">链接数：</span>${linkCount}</div>
    <div><span class="muted">时间：</span>${fmtTime(payload.timestamp) || "-"}</div>
  `;
  jsonEl.textContent = JSON.stringify(payload, null, 2);
  btnCopy.disabled = false;
  btnSave.disabled = false;
  btnCompare.disabled = !lastPdfPayload;
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

function isRestrictedUrl(url) {
  if (!url) return true;
  const lower = String(url).toLowerCase();
  const restrictedSchemes = ["chrome://", "edge://", "about:", "chrome-extension://", "devtools://", "view-source:"];
  if (restrictedSchemes.some((p) => lower.startsWith(p))) return true;
  if (lower.startsWith("https://chrome.google.com/webstore")) return true;
  if (lower.startsWith("https://chromewebstore.google.com/")) return true;
  return false;
}

async function extractViaScripting(tabId) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      function getMainText() {
        const selectors = ["main", "article", "#content", ".post", ".article"];
        for (const sel of selectors) {
          const el = document.querySelector(sel);
          if (el) return (el.innerText || "").trim();
        }
        return document.body ? (document.body.innerText || "").trim() : "";
      }

      function getTitle() {
        if (document.title) return document.title.trim();
        const h1 = document.querySelector("h1");
        return h1 ? (h1.innerText || "").trim() : "";
      }

      function getMetaDescription() {
        const meta = document.querySelector('meta[name="description"]');
        return meta ? meta.getAttribute("content") || "" : "";
      }

      function getLinks(limit = 50) {
        const links = Array.from(document.querySelectorAll("a[href]"));
        const out = [];
        for (const a of links) {
          const href = a.getAttribute("href") || "";
          if (!href || href.startsWith("javascript:")) continue;
          out.push({
            text: (a.innerText || "").trim(),
            href: href,
          });
          if (out.length >= limit) break;
        }
        return out;
      }

      return {
        url: location.href,
        title: getTitle(),
        metaDescription: getMetaDescription(),
        textSample: getMainText().slice(0, 4000),
        links: getLinks(),
        timestamp: Date.now(),
      };
    },
  });
  const payload = results && results[0] ? results[0].result : null;
  if (!payload) throw new Error("页面抽取结果为空");
  return payload;
}

async function ensureContentScript(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content_script.js"],
  });
}

async function extractFromTab() {
  const tab = await getActiveTab();
  if (!tab || typeof tab.id !== "number") throw new Error("未找到当前标签页");
  if (isRestrictedUrl(tab.url)) {
    throw new Error("当前页面不允许扩展读取内容，请换到普通网页后重试");
  }

  try {
    const payload = await extractViaScripting(tab.id);
    await chrome.runtime.sendMessage({ type: "SAVE_EXTRACT", payload });
    return payload;
  } catch (err) {
    try {
      await ensureContentScript(tab.id);
      const res = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT_NOW" });
      if (!res || res.ok !== true) throw new Error(res?.error || "提取失败");
      return res.payload;
    } catch (err2) {
      const url = String(tab.url || "");
      if (url.toLowerCase().startsWith("file://")) {
        throw new Error("无法读取本地文件页面。请在扩展详情中开启“允许访问文件网址”后重试");
      }
      const detail = String((err2 && err2.message) || (err && err.message) || err2 || err);
      throw new Error(`无法连接到页面脚本。请刷新页面后重试。原始错误：${detail}`);
    }
  }
}

async function loadLastExtract() {
  const res = await chrome.runtime.sendMessage({ type: "GET_LAST_EXTRACT" });
  if (!res || res.ok !== true) return null;
  return res.payload || null;
}

async function loadLastPdfExtract() {
  const res = await chrome.runtime.sendMessage({ type: "GET_LAST_PDF_EXTRACT" });
  if (!res || res.ok !== true) return null;
  return res.payload || null;
}

async function copyJson() {
  if (!lastPayload) return;
  const text = JSON.stringify(lastPayload, null, 2);
  await navigator.clipboard.writeText(text);
}

function saveJson() {
  if (!lastPayload) return;
  const text = JSON.stringify(lastPayload, null, 2);
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const ts = lastPayload.timestamp ? String(lastPayload.timestamp) : String(Date.now());
  a.href = url;
  a.download = `page_extract_${ts}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function renderPdf(payload) {
  lastPdfPayload = payload;
  if (!payload) {
    pdfSummaryEl.innerHTML = `<div class="muted">PDF 暂无数据</div>`;
    pdfJsonEl.textContent = "";
    btnCompare.disabled = !lastPayload;
    return;
  }
  const info = payload.source || {};
  pdfSummaryEl.innerHTML = `
    <div><span class="muted">文件：</span>${(info.file || "-")}</div>
    <div><span class="muted">页数：</span>${(info.page_count ?? "-")}（使用${info.library || "-"}, 读取${info.used_pages ?? "-" }页）</div>
  `;
  pdfJsonEl.textContent = JSON.stringify(payload.extracted || payload, null, 2);
  btnCompare.disabled = !lastPayload;
}

function normalizeTitle(s) {
  return String(s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function comparePageAndPdf(page, pdf) {
  const out = { title_match: false, title_similarity: 0, points_in_page: [] };
  const pageTitle = normalizeTitle(page?.title);
  const pdfTitle = normalizeTitle(pdf?.extracted?.doc_title);
  out.title_match = pageTitle && pdfTitle && pageTitle === pdfTitle;
  if (pageTitle && pdfTitle) {
    const a = pageTitle.split(" ");
    const b = pdfTitle.split(" ");
    const inter = a.filter((x) => b.includes(x));
    out.title_similarity = Math.round((inter.length / Math.max(a.length, 1)) * 100);
  }
  const textSample = String(page?.textSample || "");
  const points = Array.isArray(pdf?.extracted?.key_points) ? pdf.extracted.key_points : [];
  for (const p of points) {
    const hit = typeof p === "string" && p.length > 0 && textSample.includes(p);
    out.points_in_page.push({ point: p, found_in_page_textSample: !!hit });
  }
  return out;
}

function renderCompare(page, pdf) {
  const report = comparePageAndPdf(page, pdf);
  cmpSummaryEl.innerHTML = `
    <div><span class="muted">标题一致：</span>${report.title_match ? "是" : "否"}</div>
    <div><span class="muted">标题相似度：</span>${report.title_similarity}%</div>
  `;
  cmpJsonEl.textContent = JSON.stringify(report, null, 2);
}

btnExtract.addEventListener("click", async () => {
  btnExtract.disabled = true;
  setStatus("提取中...");
  try {
    const payload = await extractFromTab();
    render(payload);
    setStatus("完成");
  } catch (e) {
    setStatus(String(e && e.message ? e.message : e));
  } finally {
    btnExtract.disabled = false;
  }
});

btnCopy.addEventListener("click", async () => {
  setStatus("");
  try {
    await copyJson();
    setStatus("已复制");
  } catch (e) {
    setStatus(String(e && e.message ? e.message : e));
  }
});

btnSave.addEventListener("click", () => {
  setStatus("");
  try {
    saveJson();
  } catch (e) {
    setStatus(String(e && e.message ? e.message : e));
  }
});

pdfFileInput.addEventListener("change", () => {
  btnPdf.disabled = !(pdfFileInput.files && pdfFileInput.files[0]);
});

btnPdf.addEventListener("click", async () => {
  setStatus("PDF提取中...");
  btnPdf.disabled = true;
  try {
    const f = pdfFileInput.files && pdfFileInput.files[0];
    if (!f) throw new Error("请先选择PDF文件");
    const url = `http://127.0.0.1:8765/extract?max_pages=${encodeURIComponent(20)}&max_chars=${encodeURIComponent(
      80000
    )}`;
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/pdf" },
      body: f,
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const payload = await r.json();
    renderPdf(payload);
    try {
      await chrome.runtime.sendMessage({ type: "SAVE_PDF_EXTRACT", payload });
    } catch {}
    setStatus("PDF提取完成");
  } catch (e) {
    setStatus(String(e && e.message ? e.message : e));
  } finally {
    btnPdf.disabled = false;
  }
});

btnCompare.addEventListener("click", () => {
  if (!lastPayload || !lastPdfPayload) {
    setStatus("请先提取网页与PDF");
    return;
  }
  renderCompare(lastPayload, lastPdfPayload);
});

loadLastExtract()
  .then((payload) => {
    render(payload);
    if (payload) setStatus("已载入最近一次数据");
  })
  .catch(() => {
    render(null);
  });

loadLastPdfExtract()
  .then((payload) => {
    renderPdf(payload);
  })
  .catch(() => {
    renderPdf(null);
  });
