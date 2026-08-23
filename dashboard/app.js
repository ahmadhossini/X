const tg = window.Telegram?.WebApp;
const params = new URLSearchParams(window.location.search);
const API = params.get("api") || window.location.origin;

const state = { lang: "fa", user: null, groups: [], currentGroup: null, page: "home" };

const I18N = {
  fa: {
    home: "خانه", help: "راهنمایی", welcome_back: "خوش آمدید", your_groups: "گروه‌های شما",
    managed_groups: "گروه‌هایی که XAI MASTER در آن‌ها به شما دسترسی مدیریتی دارد", no_groups: "گروهی پیدا نشد",
    no_groups_desc: "ربات را به یک گروه اضافه کنید و دسترسی مدیریتی لازم را بدهید.", group_settings: "تنظیمات گروه",
    group_settings_desc: "امنیت و رفتار ربات را از یک صفحه کنترل کنید.", force_join: "عضویت اجباری",
    force_join_desc: "کاربر برای فعالیت باید عضو کانال‌های مشخص‌شده باشد.", required_channels_count: "تعداد کانال‌های اجباری",
    channel_links: "لینک کانال‌ها", save: "ذخیره تغییرات", security: "امنیت",
    security_desc: "قابلیت‌های امنیتی گروه را کنترل کنید.", help_title: "راهنمای XAI MASTER",
    help_intro: "مدیریت هوشمند گروه با امنیت، اتوماسیون و دستیار هوش مصنوعی.",
    help_start: "ربات را به گروه اضافه کنید، آن را مدیر کنید و سپس از دستور /panel برای باز کردن پنل مدیریت همان گروه استفاده کنید.",
    help_security: "از بخش تنظیمات می‌توانید ضد لینک، ضد اسپم، ضد فلود، فیلتر کلمات نامناسب و سایر کنترل‌های امنیتی را فعال یا غیرفعال کنید.",
    help_ai: "در گروه ربات را با نام یا @username صدا بزنید و سؤال خود را ارسال کنید. در پیام خصوصی نیز می‌توانید مستقیماً گفتگو کنید.",
    help_delete: "مدیران می‌توانند از /delete یا /حذف برای حذف پیام‌ها و از /autodelete برای تنظیم حذف خودکار استفاده کنند.",
    help_permissions: "برای عملکرد کامل، XAI MASTER باید دسترسی‌های مدیریتی موردنیاز، مخصوصاً حذف پیام‌ها را داشته باشد.",
    online: "API آنلاین", members: "عضو", active: "فعال", inactive: "غیرفعال", saved: "تغییرات ذخیره شد",
    loading: "در حال دریافت...", admin_required: "دسترسی مدیر لازم است", force_join_saved: "تنظیمات عضویت اجباری ذخیره شد."
  },
  en: {
    home: "Home", help: "Help", welcome_back: "Welcome back", your_groups: "Your groups",
    managed_groups: "Groups where XAI MASTER has access and you are an administrator", no_groups: "No groups found",
    no_groups_desc: "Add the bot to a group and grant the required administrator permissions.", group_settings: "Group settings",
    group_settings_desc: "Control security and bot behavior from one place.", force_join: "Force join",
    force_join_desc: "Users must join the selected channels before participating.", required_channels_count: "Required channels",
    channel_links: "Channel links", save: "Save changes", security: "Security",
    security_desc: "Control the group's security features.", help_title: "XAI MASTER Help",
    help_intro: "Smart group management with security, automation and an AI assistant.",
    help_start: "Add the bot to your group, promote it to administrator, then use /panel to open the management panel for that group.",
    help_security: "Use settings to enable or disable anti-link, anti-spam, anti-flood, profanity filtering and other security controls.",
    help_ai: "In a group, mention the bot by name or @username and send your question. In private chat you can talk to it directly.",
    help_delete: "Admins can use /delete or /حذف to remove messages and /autodelete to configure automatic deletion.",
    help_permissions: "For full functionality, XAI MASTER needs the required administrator permissions, especially permission to delete messages.",
    online: "API online", members: "members", active: "Enabled", inactive: "Disabled", saved: "Changes saved",
    loading: "Loading...", admin_required: "Administrator access required", force_join_saved: "Force-join settings saved."
  }
};

const FEATURES = [
  ["anti_spam", "Anti-Spam"], ["anti_flood", "Anti-Flood"], ["anti_link", "Anti-Link"], ["media_lock", "Media Lock"],
  ["forward_lock", "Forward Lock"], ["mention_lock", "Mention Lock"], ["hashtag_lock", "Hashtag Lock"], ["phone_lock", "Phone Lock"],
  ["profanity_filter", "Profanity Filter"], ["drug_filter", "Drug Filter"], ["nsfw_filter", "NSFW Filter"], ["welcome", "Welcome"],
  ["goodbye", "Goodbye"], ["clean_deleted_accounts", "Clean deleted accounts"], ["clean_bots", "Clean bots"], ["work_hours", "Work hours"],
  ["global_mute", "Global mute"], ["auto_pin", "Auto pin"], ["auto_answer", "Auto answer"], ["ai_chat", "AI chat"], ["statistics", "Statistics"]
];

function t(key) { return I18N[state.lang]?.[key] || I18N.fa[key] || key; }
function headers() { return { "Content-Type": "application/json", "X-Telegram-Init-Data": tg?.initData || "" }; }
function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
function apiUrl(path) { return `${API}${path}`; }
function showError(message) { const el = document.getElementById("error"); el.textContent = message; el.hidden = false; setTimeout(() => { el.hidden = true; }, 4500); }
function showNotice(message) { const el = document.getElementById("settings-message"); el.textContent = message; el.hidden = false; setTimeout(() => { el.hidden = true; }, 3000); }

async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || t("admin_required"));
  return data;
}

function applyLanguage() {
  document.documentElement.lang = state.lang;
  document.documentElement.dir = state.lang === "fa" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((el) => { const key = el.dataset.i18n; if (I18N[state.lang]?.[key]) el.textContent = I18N[state.lang][key]; });
  setText("api-label", t("online"));
  setText("page-subtitle", state.page === "home" ? t("home") : state.page === "help" ? t("help") : t("group_settings"));
}

function renderUser() {
  if (!state.user) return;
  const fullName = [state.user.first_name, state.user.last_name].filter(Boolean).join(" ") || "User";
  setText("user-name", fullName);
  setText("user-username", state.user.username ? `@${state.user.username}` : `ID ${state.user.id}`);
  const photo = document.getElementById("user-photo"), fallback = document.getElementById("user-avatar-fallback");
  if (state.user.photo_url) { photo.src = state.user.photo_url; photo.hidden = false; fallback.hidden = true; }
  else { photo.hidden = true; fallback.hidden = false; fallback.textContent = fullName.charAt(0).toUpperCase(); }
}

function renderGroups() {
  const list = document.getElementById("groups-list"); list.innerHTML = "";
  setText("group-count", String(state.groups.length));
  document.getElementById("groups-empty").hidden = state.groups.length !== 0;
  for (const group of state.groups) {
    const card = document.createElement("button"); card.type = "button"; card.className = "group-card";
    const fallback = (group.title || "G").charAt(0).toUpperCase();
    const avatar = group.photo_url ? `<img class="avatar avatar-lg" src="${group.photo_url}" alt="group">` : `<div class="avatar avatar-lg avatar-fallback">${fallback}</div>`;
    card.innerHTML = `${avatar}<div class="group-info"><h3></h3><div class="group-meta"><span class="member-value"></span><span>•</span><span>${state.lang === "fa" ? "مدیر" : "Admin"}</span></div></div><span class="group-arrow">‹</span>`;
    card.querySelector("h3").textContent = group.title || "Group";
    card.querySelector(".member-value").textContent = `${group.member_count || 0} ${t("members")}`;
    card.addEventListener("click", () => openGroup(group.id));
    list.appendChild(card);
  }
}

function setSwitch(button, enabled) { button.classList.toggle("on", Boolean(enabled)); }

function renderSettings(settings) {
  const list = document.getElementById("settings-list"); list.innerHTML = "";
  for (const [feature, label] of FEATURES) {
    const enabled = Boolean(settings[feature]);
    const row = document.createElement("div"); row.className = "setting";
    const info = document.createElement("div");
    info.innerHTML = `<div class="setting-name"></div><div class="setting-state"></div>`;
    info.querySelector(".setting-name").textContent = label;
    info.querySelector(".setting-state").textContent = enabled ? t("active") : t("inactive");
    const button = document.createElement("button"); button.type = "button"; button.className = "switch"; setSwitch(button, enabled);
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const data = await request(`/api/groups/${encodeURIComponent(state.currentGroup.id)}/settings`, { method: "POST", body: JSON.stringify({ feature, enabled: !enabled }) });
        renderSettings(data.settings); showNotice(t("saved"));
      } catch (error) { showError(error.message); button.disabled = false; }
    });
    row.append(info, button); list.appendChild(row);
  }
}

async function loadGroupPhoto(group) {
  const photo = document.getElementById("group-photo"), fallback = document.getElementById("group-avatar-fallback");
  if (!group.photo_url) { photo.hidden = true; fallback.hidden = false; fallback.textContent = (group.title || "G").charAt(0).toUpperCase(); return; }
  try {
    const response = await fetch(apiUrl(group.photo_url), { headers: { "X-Telegram-Init-Data": tg?.initData || "" } });
    if (!response.ok) throw new Error("photo unavailable");
    const blob = await response.blob();
    photo.src = URL.createObjectURL(blob); photo.hidden = false; fallback.hidden = true;
  } catch (_) { photo.hidden = true; fallback.hidden = false; fallback.textContent = (group.title || "G").charAt(0).toUpperCase(); }
}

function renderGroup(group, settings) {
  setText("group-name", group.title || "Group");
  setText("group-username", group.username ? `@${group.username}` : (state.lang === "fa" ? "گروه تلگرام" : "Telegram group"));
  setText("group-members", `${group.member_count || 0} ${t("members")}`);
  loadGroupPhoto(group);
  setSwitch(document.getElementById("force-join-switch"), settings.force_join);
  document.getElementById("force-join-count").value = settings.force_join_count || 0;
  document.getElementById("force-join-channels").value = (settings.force_join_channels || []).join("\n");
  renderSettings(settings);
}

async function openGroup(chatId) {
  try {
    const data = await request(`/api/groups/${encodeURIComponent(chatId)}`);
    state.currentGroup = data.group; state.page = "settings";
    showPage("settings"); renderGroup(data.group, data.settings);
    if (tg?.BackButton) { tg.BackButton.show(); }
  } catch (error) { showError(error.message); }
}

function showPage(page) {
  state.page = page;
  document.querySelectorAll(".page").forEach((el) => { el.hidden = true; el.classList.remove("active"); });
  const target = document.getElementById(`page-${page}`); if (!target) return; target.hidden = false; target.classList.add("active");
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
  applyLanguage();
  if (page === "home" && tg?.BackButton) tg.BackButton.hide();
}

async function loadHome() {
  const [me, groups] = await Promise.all([request("/api/me"), request("/api/me/groups")]);
  state.user = me; state.lang = me.language || "fa"; state.groups = groups.groups || [];
  renderUser(); renderGroups(); applyLanguage();
}

async function init() {
  if (!tg?.initData) { showError("Mini App باید از داخل تلگرام باز شود."); return; }
  tg.ready(); tg.expand();
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => showPage(button.dataset.page)));
  document.getElementById("back-home").addEventListener("click", () => showPage("home"));
  if (tg?.BackButton) tg.BackButton.onClick(() => showPage("home"));

  document.getElementById("force-join-switch").addEventListener("click", async () => {
    const enabled = !document.getElementById("force-join-switch").classList.contains("on");
    try {
      const data = await request(`/api/groups/${encodeURIComponent(state.currentGroup.id)}/settings`, { method: "POST", body: JSON.stringify({ feature: "force_join", enabled }) });
      setSwitch(document.getElementById("force-join-switch"), data.settings.force_join); showNotice(t("saved"));
    } catch (error) { showError(error.message); }
  });

  document.getElementById("save-force-join").addEventListener("click", async () => {
    const count = Number(document.getElementById("force-join-count").value || 0);
    const channels = document.getElementById("force-join-channels").value.split(/\n|,/).map(v => v.trim()).filter(Boolean);
    try {
      const data = await request(`/api/groups/${encodeURIComponent(state.currentGroup.id)}/config`, { method: "POST", body: JSON.stringify({ force_join_count: count, force_join_channels: channels }) });
      renderGroup(state.currentGroup, data.settings); showNotice(t("force_join_saved"));
    } catch (error) { showError(error.message); }
  });

  try {
    await loadHome();
    const chatId = params.get("chat_id");
    if (chatId) await openGroup(chatId);
  } catch (error) { showError(error.message || "Connection error"); }
}

init();
