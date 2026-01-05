const LAST_EXTRACT_KEY = "last_extract";

async function setLastExtract(payload) {
  await chrome.storage.local.set({ [LAST_EXTRACT_KEY]: payload });
}

async function getLastExtract() {
  const res = await chrome.storage.local.get([LAST_EXTRACT_KEY]);
  return res[LAST_EXTRACT_KEY] ?? null;
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
});

