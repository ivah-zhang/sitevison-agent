const API = {
  async request(path, options = {}) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (_) { /* 回應非 JSON 時沿用狀態文字 */ }
      throw new Error(detail);
    }
    return response.status === 204 ? null : response.json();
  },

  get(path) {
    return API.request(path);
  },

  post(path, body) {
    return API.request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
  },

  postForm(path, formData) {
    return API.request(path, { method: "POST", body: formData });
  },
};

function toast(message, isError = false) {
  const host = document.getElementById("toast");
  if (!host) return;
  const item = document.createElement("div");
  if (isError) item.className = "err";
  item.textContent = message;
  host.appendChild(item);
  setTimeout(() => item.remove(), 4200);
}

async function withBusy(button, task) {
  const original = button ? button.textContent : null;
  if (button) {
    button.disabled = true;
    button.textContent = "處理中…";
  }
  try {
    return await task();
  } catch (error) {
    toast(error.message, true);
    throw error;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

function markActiveTab() {
  const current = location.pathname.split("/").pop() || "index.html";
  document.querySelectorAll("nav.tabs a").forEach((link) => {
    if (link.getAttribute("href") === current) link.classList.add("active");
  });
}

async function showDetectorBadge() {
  const badge = document.getElementById("detector-badge");
  if (!badge) return;
  try {
    const health = await API.get("/api/health");
    const isMock = health.detector === "mock";
    badge.classList.add(isMock ? "mock" : "live");
    badge.textContent = isMock ? "● 模擬偵測器 mock" : `● 實測模型 ${health.detector}`;
    badge.title = isMock
      ? "目前使用模擬偵測器，結果不代表真實識別準確度"
      : "目前使用真實模型偵測";
  } catch (_) {
    badge.classList.add("down");
    badge.textContent = "● 後端未連線";
  }
}

function formatTime(value) {
  if (!value) return "—";
  return String(value).slice(0, 19).replace("T", " ");
}

function openLightbox(src) {
  let dialog = document.getElementById("lightbox");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "lightbox";
    dialog.className = "lightbox";
    dialog.innerHTML = "<img alt='相片放大'>";
    dialog.addEventListener("click", () => dialog.close());
    document.body.appendChild(dialog);
  }
  dialog.querySelector("img").src = src;
  dialog.showModal();
}

document.addEventListener("DOMContentLoaded", () => {
  markActiveTab();
  showDetectorBadge();
});
