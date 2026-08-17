(() => {
  const tg = window.Telegram?.WebApp;
  tg?.ready?.();
  tg?.expand?.();

  const API = "";
  const user = tg?.initDataUnsafe?.user || {};
  const state = {
    route: "home",
    groups: [],
    chat: null,
    settings: {},
    stats: {},
    market: [],
    publicMarket: null,
    loading: false,
    lang: (user.language_code || "fa").toLowerCase().startsWith("en") ? "en" : "fa",
  };

  const T = {
    fa: {
      home: "خانه", market: "بازار", groups: "گروه‌ها و کانال‌ها", profile: "پروفایل",
      workspaces: "فضاهای قابل مدیریت", managed: "گروه‌ها و کانال‌های من",
      managedHint: "فقط چت‌هایی که ربات در آن‌ها فعال است و شما دسترسی مدیریتی دارید.",
      empty: "فضای مدیریتی پیدا نشد", emptyHint: "XAIMASTER را به‌عنوان مدیر به گروه یا کانال اضافه کنید و دوباره برنامه را باز کنید.",
      marketTitle: "بازار", crypto: "ارزهای دیجیتال", gold: "طلا", dollar: "دلار", change: "تغییر ۲۴ ساعته",
      live: "زنده", refresh: "به‌روزرسانی", dashboard: "داشبورد", security: "امنیت", activity: "فعالیت",
      members: "اعضا", messages: "پیام‌ها", deleted: "حذف‌شده", warnings: "اخطارها", restricted: "محدودشده",
      settings: "تنظیمات امنیتی", saved: "ذخیره شد", saving: "در حال ذخیره", error: "خطا در دریافت اطلاعات",
      noActivity: "هنوز داده فعالیت ثبت نشده است.", back: "بازگشت", channel: "کانال", group: "گروه",
      antiLink: "ضد لینک", antiUsername: "ضد یوزرنیم", antiHashtag: "ضد هشتگ", antiForward: "ضد فوروارد",
      antiSpam: "ضد اسپم", antiFlood: "ضد فلود", bannedWords: "کلمات ممنوع", phone: "ضد شماره",
      drug: "فیلتر مواد مخدر", nsfw: "فیلتر محتوای نامناسب", photo: "قفل عکس", video: "قفل ویدیو",
      document: "قفل فایل", audio: "قفل صوت", voice: "قفل ویس", sticker: "قفل استیکر", animation: "قفل GIF",
      poll: "قفل نظرسنجی", location: "قفل موقعیت", contact: "قفل مخاطب", language: "زبان", telegramId: "شناسه Telegram",
      role: "کاربر", online: "آنلاین", profileHint: "اطلاعات حساب Telegram شما",
    },
    en: {
      home: "Home", market: "Market", groups: "Groups & Channels", profile: "Profile",
      workspaces: "Managed spaces", managed: "My groups & channels",
      managedHint: "Only chats where the bot is active and you have administrator access are shown.",
      empty: "No managed spaces", emptyHint: "Add XAIMASTER as an administrator to a group or channel, then reopen the app.",
      marketTitle: "Market", crypto: "Crypto", gold: "Gold", dollar: "USD", change: "24h change",
      live: "Live", refresh: "Refresh", dashboard: "Dashboard", security: "Security", activity: "Activity",
      members: "Members", messages: "Messages", deleted: "Deleted", warnings: "Warnings", restricted: "Restricted",
      settings: "Security settings", saved: "Saved", saving: "Saving", error: "Unable to load data",
      noActivity: "No activity data has been recorded yet.", back: "Back", channel: "Channel", group: "Group",
      antiLink: "Anti Link", antiUsername: "Anti Username", antiHashtag: "Anti Hashtag", antiForward: "Anti Forward",
      antiSpam: "Anti Spam", antiFlood: "Anti Flood", bannedWords: "Banned Words", phone: "Phone Filter",
      drug: "Drug Filter", nsfw: "Content Filter", photo: "Photo Lock", video: "Video Lock",
      document: "File Lock", audio: "Audio Lock", voice: "Voice Lock", sticker: "Sticker Lock", animation: "GIF Lock",
      poll: "Poll Lock", location: "Location Lock", contact: "Contact Lock", language: "Language", telegramId: "Telegram ID",
      role: "User", online: "Online", profileHint: "Your Telegram account information",
    },
  };

  const t = () => T[state.lang];
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const headers = () => ({ "X-Telegram-Init-Data": tg?.initData || "" });

  const icon = (type) => {
    const paths = {
      back: "M15 18l-6-6 6-6", arrow: "M9 18l6-6-6-6", chart: "M4 17l5-5 4 3 7-8",
      users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
      shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
      user: "M20 21a8 8 0 0 0-16 0M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
      group: "M4 7h16v10H4zM8 7V5h8v2", channel: "M6 4h12v16H6z",
    };
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="${paths[type] || paths.chart}"/></svg>`;
  };

  async function get(path) {
    const response = await fetch(`${API}${path}`, { headers: headers(), cache: "no-store" });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || t().error);
    return response.json();
  }

  function setRoute(route) {
    state.route = route;
    document.querySelectorAll(".page").forEach(page => page.classList.remove("active-page"));
    const target = $(route === "chat" ? "chatPage" : `${route}Page`);
    target?.classList.add("active-page");
    document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.route === route));
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (route === "home") renderHome();
    if (route === "market") renderMarket();
    if (route === "groups") renderGroups();
    if (route === "profile") renderProfile();
  }

  async function loadGroups() {
    try { state.groups = (await get("/api/miniapp/groups")).groups || []; }
    catch { state.groups = []; }
  }

  async function renderHome() {
    const el = $("homePage");
    el.innerHTML = `<div class="page-head"><div><span class="eyebrow">XAI MASTER</span><h1>${escapeHtml(user.first_name || "User")}</h1><p>${t().managedHint}</p></div><button class="icon-button" data-profile>${icon("user")}</button></div><section class="section"><div class="section-head"><div><span class="eyebrow">${t().workspaces}</span><h2>${t().managed}</h2></div><span class="count-pill">${state.groups.length}</span></div><div id="homeSpaces"></div></section>`;
    const list = $("homeSpaces");
    if (!state.groups.length) {
      list.innerHTML = `<div class="empty-card">${icon("shield")}<h3>${t().empty}</h3><p>${t().emptyHint}</p></div>`;
    } else {
      list.innerHTML = state.groups.map(chatCard).join("");
      list.querySelectorAll("[data-chat]").forEach(node => node.addEventListener("click", () => openChat(node.dataset.chat)));
    }
    el.querySelector("[data-profile]")?.addEventListener("click", () => setRoute("profile"));
  }

  function chatCard(chat) {
    const type = chat.type === "channel" ? t().channel : t().group;
    return `<button class="space-card" data-chat="${escapeHtml(chat.chat_id)}"><span class="space-symbol">${icon(chat.type === "channel" ? "channel" : "group")}</span><span class="space-copy"><strong>${escapeHtml(chat.title)}</strong><small>${type}</small><span class="space-meta">${chat.member_count ?? "—"} ${t().members} · ${chat.message_count ?? "0"} ${t().messages}</span></span><span class="chevron">${icon("arrow")}</span></button>`;
  }

  async function renderMarket() {
    const el = $("marketPage");
    el.innerHTML = `<div class="page-head"><div><span class="eyebrow">MARKET</span><h1>${t().marketTitle}</h1><p>${t().live}</p></div><button id="marketRefresh" class="outline-button">${t().refresh}</button></div><div class="market-grid" id="marketCards"><div class="loading-card">Loading...</div></div><section class="section"><div class="section-head"><div><span class="eyebrow">${t().crypto}</span><h2>${t().change}</h2></div></div><div class="chart-panel" id="marketChart">Loading...</div></section>`;
    $("marketRefresh").addEventListener("click", renderMarket);
    try {
      const [crypto, publicData] = await Promise.all([get("/api/market/crypto"), fetch(`${API}/api/market/public`, { cache: "no-store" }).then(r => r.ok ? r.json() : {})]);
      state.market = crypto || []; state.publicMarket = publicData || {};
      const selected = [state.publicMarket?.gold_usd ? {symbol:t().gold, price_usd:state.publicMarket.gold_usd, change_24h:null} : null, ...state.market.slice(0,5)].filter(Boolean);
      $("marketCards").innerHTML = selected.map(item => `<article class="market-card"><div><span class="market-symbol">${escapeHtml(item.symbol)}</span><strong>${formatPrice(item.price_usd)}</strong></div><span class="change ${Number(item.change_24h) >= 0 ? "up" : "down"}">${item.change_24h == null ? "—" : `${Number(item.change_24h).toFixed(2)}%`}</span></article>`).join("");
      $("marketChart").innerHTML = buildMarketChart(state.market.slice(0, 8));
    } catch {
      $("marketCards").innerHTML = `<div class="empty-card">${icon("chart")}<h3>${t().error}</h3></div>`;
      $("marketChart").textContent = t().error;
    }
  }

  function formatPrice(value) {
    if (value == null) return "—";
    return new Intl.NumberFormat(state.lang === "fa" ? "fa-IR" : "en-US", { maximumFractionDigits: 4 }).format(Number(value));
  }

  function buildMarketChart(items) {
    if (!items.length) return `<p class="muted">No market data.</p>`;
    const max = Math.max(...items.map(x => Number(x.change_24h || 0)), 1);
    const min = Math.min(...items.map(x => Number(x.change_24h || 0)), -1);
    const points = items.map((x, i) => {
      const xPos = 10 + (i * 280 / Math.max(1, items.length - 1));
      const yPos = 85 - ((Number(x.change_24h || 0) - min) / (max - min)) * 65;
      return `${xPos.toFixed(1)},${yPos.toFixed(1)}`;
    }).join(" ");
    return `<svg viewBox="0 0 300 100" class="chart-svg" preserveAspectRatio="none"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg><div class="chart-labels">${items.map(x => `<span>${escapeHtml(x.symbol)}</span>`).join("")}</div>`;
  }

  async function renderGroups() {
    const el = $("groupsPage");
    el.innerHTML = `<div class="page-head"><div><span class="eyebrow">WORKSPACES</span><h1>${t().groups}</h1><p>${t().managedHint}</p></div></div><div class="section" id="groupsList">${state.groups.length ? state.groups.map(chatCard).join("") : `<div class="empty-card">${icon("group")}<h3>${t().empty}</h3><p>${t().emptyHint}</p></div>`}</div>`;
    el.querySelectorAll("[data-chat]").forEach(node => node.addEventListener("click", () => openChat(node.dataset.chat)));
  }

  async function openChat(chatId) {
    state.route = "chat";
    document.querySelectorAll(".page").forEach(page => page.classList.remove("active-page"));
    $("chatPage").classList.add("active-page");
    document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
    const el = $("chatPage");
    el.innerHTML = `<button class="back-button" id="chatBack">${icon("back")} ${t().back}</button><div id="chatBody"><div class="loading-card">Loading...</div></div>`;
    $("chatBack").addEventListener("click", () => setRoute("home"));
    try {
      const [chat, settings, stats] = await Promise.all([get(`/api/miniapp/groups/${chatId}`), get(`/api/miniapp/groups/${chatId}/settings`), get(`/api/miniapp/groups/${chatId}/stats`)]);
      state.chat = chat; state.settings = settings; state.stats = stats;
      renderChatBody(chatId);
    } catch (error) {
      $("chatBody").innerHTML = `<div class="empty-card">${icon("shield")}<h3>${escapeHtml(error.message)}</h3></div>`;
    }
  }

  function renderChatBody(chatId) {
    const chat = state.chat, s = state.stats || {};
    const rules = [
      ["anti_link", t().antiLink], ["mention_lock", t().antiUsername], ["hashtag_lock", t().antiHashtag], ["forward_lock", t().antiForward],
      ["anti_spam", t().antiSpam], ["anti_flood", t().antiFlood], ["profanity_filter", t().bannedWords], ["phone_lock", t().phone],
      ["drug_filter", t().drug], ["nsfw_filter", t().nsfw], ["photo_lock", t().photo], ["video_lock", t().video],
      ["document_lock", t().document], ["audio_lock", t().audio], ["voice_lock", t().voice], ["sticker_lock", t().sticker],
      ["animation_lock", t().animation], ["poll_lock", t().poll], ["location_lock", t().location], ["contact_lock", t().contact],
    ];
    $("chatBody").innerHTML = `<section class="chat-hero"><span class="space-symbol">${icon(chat.type === "channel" ? "channel" : "group")}</span><div><span class="eyebrow">${escapeHtml(chat.type === "channel" ? t().channel : t().group)}</span><h1>${escapeHtml(chat.title)}</h1></div></section><div class="metric-grid"><div class="metric"><small>${t().members}</small><strong>${chat.member_count ?? "—"}</strong></div><div class="metric"><small>${t().messages}</small><strong>${s.messages ?? 0}</strong></div><div class="metric"><small>${t().deleted}</small><strong>${s.deleted ?? 0}</strong></div><div class="metric"><small>${t().warnings}</small><strong>${s.warnings ?? 0}</strong></div></div><section class="section"><div class="section-head"><div><span class="eyebrow">${t().activity}</span><h2>${t().messages}</h2></div></div><div class="chart-panel">${buildActivityChart(s.chart || [])}</div></section><section class="section"><div class="section-head"><div><span class="eyebrow">SECURITY</span><h2>${t().settings}</h2></div></div><div class="settings-list">${rules.map(([key, label]) => `<label class="setting-row"><span><strong>${label}</strong><small>${escapeHtml(ruleDescription(key))}</small></span><input type="checkbox" data-setting="${key}" ${state.settings[key] ? "checked" : ""}><i></i></label>`).join("')}</div></section>`;
    $("chatBody").querySelectorAll("[data-setting]").forEach(input => input.addEventListener("change", () => updateSetting(chatId, input.dataset.setting, input.checked)));
  }

  function ruleDescription(key) {
    const descriptions = {
      anti_link: "HTTP, Telegram and website links", mention_lock: "Telegram usernames", hashtag_lock: "Hashtags", forward_lock: "Forwarded messages",
      anti_spam: "Repeated messages", anti_flood: "Rapid message bursts", profanity_filter: "Configured banned words", phone_lock: "Phone numbers",
      drug_filter: "Drug-related terms", nsfw_filter: "Explicit terms", photo_lock: "Photo messages", video_lock: "Video messages",
      document_lock: "Files and documents", audio_lock: "Audio messages", voice_lock: "Voice messages", sticker_lock: "Stickers",
      animation_lock: "GIF and animations", poll_lock: "Polls", location_lock: "Locations", contact_lock: "Contacts",
    };
    return descriptions[key] || "Security rule";
  }

  function buildActivityChart(points) {
    if (!points.length) return `<p class="muted">${t().noActivity}</p>`;
    const max = Math.max(1, ...points.map(p => Number(p.messages || 0)));
    const bars = points.map(p => `<div class="activity-bar" title="${escapeHtml(p.date)}: ${p.messages || 0}" style="height:${Math.max(4, Number(p.messages || 0) / max * 100)}%"></div>`).join("");
    return `<div class="activity-chart">${bars}</div><div class="chart-labels">${points.map(p => `<span>${escapeHtml(p.date.slice(5))}</span>`).join("")}</div>`;
  }

  async function updateSetting(chatId, feature, enabled) {
    try {
      const response = await fetch(`${API}/api/miniapp/groups/${chatId}/settings`, { method: "PATCH", headers: { ...headers(), "Content-Type": "application/json" }, body: JSON.stringify({ feature, enabled }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to save setting");
      state.settings[feature] = enabled;
      tg?.HapticFeedback?.notificationOccurred?.("success");
    } catch (error) {
      tg?.HapticFeedback?.notificationOccurred?.("error");
      renderChatBody(chatId);
      alert(error.message || "Unable to save setting");
    }
  }

  function renderProfile() {
    const el = $("profilePage");
    const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ") || "User";
    el.innerHTML = `<button class="back-button" data-home>${icon("back")} ${t().back}</button><section class="profile-card"><div class="profile-large">${user.photo_url ? `<img src="${escapeHtml(user.photo_url)}" alt="">` : escapeHtml(fullName.slice(0,1))}</div><h1>${escapeHtml(fullName)}</h1><p>${escapeHtml(user.username ? `@${user.username}` : "Telegram profile")}</p><div class="profile-info"><div><span>${t().telegramId}</span><strong>${escapeHtml(user.id || "—")}</strong></div><div><span>${t().language}</span><strong>${state.lang === "fa" ? "فارسی" : "English"}</strong></div><div><span>${t().role}</span><strong>${t().role}</strong></div></div></section>`;
    el.querySelector("[data-home]").addEventListener("click", () => setRoute("home"));
  }

  $("profileButton")?.addEventListener("click", () => setRoute("profile"));
  document.querySelectorAll("[data-route]").forEach(button => button.addEventListener("click", () => setRoute(button.dataset.route)));

  if (user.photo_url) { $("profileImage").src = user.photo_url; $("profileImage").classList.remove("hidden"); $("profileInitial").classList.add("hidden"); }
  $("profileInitial").textContent = (user.first_name || "A").slice(0, 1).toUpperCase();
  $("online").textContent = t().online;
  $("navHome").textContent = t().home; $("navMarket").textContent = t().market; $("navGroups").textContent = t().groups;

  (async () => { await loadGroups(); setRoute("home"); })();
})();
