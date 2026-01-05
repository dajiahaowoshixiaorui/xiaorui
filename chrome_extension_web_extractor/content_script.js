function getMainText() {
  const selectors = ["main", "article", "#content", ".post", ".article"];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) {
      return el.innerText.trim();
    }
  }
  return document.body ? document.body.innerText.trim() : "";
}

function getTitle() {
  if (document.title) return document.title.trim();
  const h1 = document.querySelector("h1");
  return h1 ? h1.innerText.trim() : "";
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

function extractPageInfo() {
  return {
    url: location.href,
    title: getTitle(),
    metaDescription: getMetaDescription(),
    textSample: getMainText().slice(0, 4000),
    links: getLinks(),
    timestamp: Date.now(),
  };
}

async function saveExtract() {
  const payload = extractPageInfo();
  try {
    await chrome.runtime.sendMessage({ type: "SAVE_EXTRACT", payload });
  } catch (e) {
  }
}

saveExtract();

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message !== "object") return;
  if (message.type !== "EXTRACT_NOW") return;
  const payload = extractPageInfo();
  chrome.runtime
    .sendMessage({ type: "SAVE_EXTRACT", payload })
    .then(() => sendResponse({ ok: true, payload }))
    .catch((err) => sendResponse({ ok: false, error: String(err) }));
  return true;
});
