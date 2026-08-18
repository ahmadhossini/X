const tg = window.Telegram?.WebApp;
const statusEl = document.getElementById("status");
const groupStatusEl = document.getElementById("group-status");
const settingsList = document.getElementById("settings-list");
const errorEl = document.getElementById("error");

const FEATURES = [
  ["anti_link", "Anti-Link"],
  ["anti_flood", "Anti-Flood"],
  ["anti_spam", "Anti-Spam"],
  ["forward_lock", "Forward Lock"],
  ["mention_lock", "Mention Lock"],
  ["hashtag_lock", "Hashtag Lock"],
  ["phone_lock", "Phone Lock"],
  ["profanity_filter", "Profanity Filter"],
  ["drug_filter", "Drug Filter"],
  ["nsfw_filter", "NSFW Filter"]
];

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearError() {
  errorEl.hidden = true;
  errorEl.textContent = "";
}

function getChatId() {
  const params = new URLSearchParams(window.location.search);
  const direct = params.get("chat_id");
  if (direct) return direct;

  const startParam = tg?.initDataUnsafe?.start_param || "";
  if (startParam.startsWith("panel_")) {
    return startParam.slice("panel_".length);
  }

  return "";
}

function apiBase() {
  const params = new URLSearchParams(window.location.search);
  return params.get("api") || "";
}

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": tg?.initData || ""
  };
}

async function loadMarket() {
  try {
    const health = await fetch(`${apiBase()}/health`);
    if (!health.ok) throw new Error("API unavailable");
    statusEl.textContent = "آنلاین";

    const response = await fetch(`${apiBase()}/api/market/crypto`);
    if (!response.ok) throw new Error("Market unavailable");

    const assets = await response.json();
    for (const asset of assets) {
      const element = document.getElementById(asset.symbol.toLowerCase());
      if (element && asset.price_usd != null) {
        element.textContent = `$${Number(asset.price_usd).toLocaleString()}`;
      }
    }
  } catch (error) {
    statusEl.textContent = "خطا در اتصال";
    console.error(error);
  }
}

function renderSettings(values, chatId) {
  settingsList.innerHTML = "";

  for (const [feature, label] of FEATURES) {
    const enabled = Boolean(values[feature]);
    const row = document.createElement("div");
    row.className = "setting";

    const info = document.createElement("div");
    const name = document.createElement("div");
    name.className = "setting-name";
    name.textContent = label;

    const state = document.createElement("div");
    state.className = "setting-state";
    state.textContent = enabled ? "فعال" : "غیرفعال";

    info.append(name, state);

    const button = document.createElement("button");
    button.className = `switch${enabled ? " on" : ""}`;
    button.type = "button";
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", String(enabled));

    button.addEventListener("click", async () => {
      clearError();
      button.disabled = true;
      try {
        const response = await fetch(
          `${apiBase()}/api/groups/${encodeURIComponent(chatId)}/settings`,
          {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({
              feature,
              enabled: !Boolean(values[feature])
            })
          }
        );

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "خطا در ذخیره تنظیمات");
        }

        renderSettings(data.settings, chatId);
        groupStatusEl.textContent = "تنظیمات ذخیره شد";
      } catch (error) {
        showError(error.message || "خطا در ذخیره تنظیمات");
        button.disabled = false;
      }
    });

    row.append(info, button);
    settingsList.appendChild(row);
  }
}

async function loadSettings() {
  let chatId = getChatId();

  if (!tg?.initData) {
    groupStatusEl.textContent = "فقط از داخل تلگرام قابل استفاده است";
    showError("Mini App باید از داخل Telegram باز شود.");
    return;
  }

  if (!chatId || !String(chatId).startsWith("-")) {
    groupStatusEl.textContent = "گروه انتخاب نشده";
    showError("این پنل باید از دستور /panel همان گروه باز شود.");
    return;
  }

  try {
    const response = await fetch(
      `${apiBase()}/api/groups/${encodeURIComponent(chatId)}/settings`,
      { headers: headers() }
    );

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "دسترسی به تنظیمات ممکن نیست");
    }

    groupStatusEl.textContent = `مدیریت گروه فعال است • ${data.chat_id}`;
    renderSettings(data.settings, chatId);
  } catch (error) {
    groupStatusEl.textContent = "دسترسی رد شد";
    showError(error.message || "خطا در دریافت تنظیمات");
  }
}

function initTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
}

initTelegram();
loadMarket();
loadSettings();
