const LAST_EXTRACT_KEY = "last_extract";
const LAST_PDF_EXTRACT_KEY = "last_pdf_extract";
const PDF_AGENT_URL = "http://127.0.0.1:8765/extract";

async function setLastExtract(payload) {
  await chrome.storage.local.set({ [LAST_EXTRACT_KEY]: payload });
}

async function getLastExtract() {
  const res = await chrome.storage.local.get([LAST_EXTRACT_KEY]);
  return res[LAST_EXTRACT_KEY] ?? null;
}

async function setLastPdfExtract(payload) {
  await chrome.storage.local.set({ [LAST_PDF_EXTRACT_KEY]: payload });
}

async function getLastPdfExtract() {
  const res = await chrome.storage.local.get([LAST_PDF_EXTRACT_KEY]);
  return res[LAST_PDF_EXTRACT_KEY] ?? null;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message !== "object") return;

  if (message.type === "SAVE_EXTRACT") {
    setLastExtract(message.payload)
      .then(() => sendResponse({ ok: true }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }

  if (message.type === "GET_LAST_EXTRACT") {
    getLastExtract()
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }

  if (message.type === "EXTRACT_PDF") {
    let buffer = message.buffer;
    const blob = message.blob;
    const maxPages = message.maxPages ?? 20;
    const maxChars = message.maxChars ?? 80000;
    const toArrayBuffer = async (val, blobVal) => {
      if (blobVal && typeof blobVal.arrayBuffer === "function") {
        try {
          return await blobVal.arrayBuffer();
        } catch (e) {}
      }
      if (val instanceof ArrayBuffer) return val;
      if (ArrayBuffer.isView(val) && val.buffer instanceof ArrayBuffer) return val.buffer;
      if (val && typeof val === "object" && typeof val.byteLength === "number" && val.buffer instanceof ArrayBuffer)
        return val.buffer;
      // handle {data: Uint8Array-like}
      if (val && Array.isArray(val)) {
        try {
          return new Uint8Array(val).buffer;
        } catch (e) {}
      }
      return null;
    };
    Promise.resolve()
      .then(() => toArrayBuffer(buffer, blob))
      .then((ab) => {
        if (!ab) throw new Error("buffer_invalid");
        return fetch(
          `${PDF_AGENT_URL}?max_pages=${encodeURIComponent(maxPages)}&max_chars=${encodeURIComponent(maxChars)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/pdf" },
            body: ab,
          }
        );
      })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const payload = await r.json();
        await setLastPdfExtract(payload);
        sendResponse({ ok: true, payload });
      })
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }

  if (message.type === "GET_LAST_PDF_EXTRACT") {
    getLastPdfExtract()
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }

  if (message.type === "SAVE_PDF_EXTRACT") {
    setLastPdfExtract(message.payload)
      .then(() => sendResponse({ ok: true }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }
});
