(() => {
  const tg = window.Telegram?.WebApp;
  tg?.ready?.();
  tg?.expand?.();

  const user = tg?.initDataUnsafe?.user || {};
  const state = { lang: (user.language_code || "fa").toLowerCase().startsWith("en") ? "en" : "fa", groups: [], settings: {}, stats: {}, chat: null };
  const API = "";
  const $ = id => document.getElementById(id);
  const t = () => state.lang === "fa" ? {
    home: "خانه", market: "بازار", groups: "گروه‌ها و کانال‌ها", managed: "گروه‌ها و کانال‌های من", hint: "فقط چت‌هایی که ربات در آن‌ها فعال است و شما دسترسی مدیریتی دارید.", empty: "فضای مدیریتی پیدا نشد", emptyHint: "XAIMASTER را به‌عنوان مدیر به گروه یا کانال اضافه کنید و دوباره برنامه را باز کنید.", members: "اعضا", messages: "پیام‌ها", channel: "کانال", group: "گروه", back: "بازگشت", refresh: "به‌روزرسانی", live: "زنده", security: "تنظیمات امنیتی", activity: "فعالیت", deleted: "حذف‌شده", warnings: "اخطارها", crypto: "ارزهای دیجیتال", gold: "طلا", antiLink: "ضد لینک", antiUsername: "ضد یوزرنیم", antiHashtag: "ضد هشتگ", antiForward: "ضد فوروارد", antiSpam: "ضد اسپم", antiFlood: "ضد فلود", bannedWords: "کلمات ممنوع", phone: "ضد شماره", drug: "فیلتر مواد مخدر", nsfw: "فیلتر محتوای نامناسب", photo: "قفل عکس", video: "قفل ویدیو", document: "قفل فایل", audio: "قفل صوت", voice: "قفل ویس", sticker: "قفل استیکر", animation: "قفل GIF", poll: "قفل نظرسنجی", location: "قفل موقعیت", contact: "قفل مخاطب", profile: "پروفایل", telegramId: "شناسه Telegram", language: "زبان", role: "کاربر", noActivity: "هنوز داده فعالیت ثبت نشده است."
  } : {
    home: "Home", market: "Market", groups: "Groups & Channels", managed: "My groups & channels", hint: "Only chats where the bot is active and you have administrator access are shown.", empty: "No managed spaces", emptyHint: "Add XAIMASTER as an administrator to a group or channel, then reopen the app.", members: "Members", messages: "Messages", channel: "Channel", group: "Group", back: "Back", refresh: "Refresh", live: "Live", security: "Security settings", activity: "Activity", deleted: "Deleted", warnings: "Warnings", crypto: "Crypto", gold: "Gold", antiLink: "Anti Link", antiUsername: "Anti Username", antiHashtag: "Anti Hashtag", antiForward: "Anti Forward", antiSpam: "Anti Spam", antiFlood: "Anti Flood", bannedWords: "Banned Words", phone: "Phone Filter", drug: "Drug Filter", nsfw: "Content Filter", photo: "Photo Lock", video: "Video Lock", document: "File Lock", audio: "Audio Lock", voice: "Voice Lock", sticker: "Sticker Lock", animation: "GIF Lock", poll: "Poll Lock", location: "Location Lock", contact: "Contact Lock", profile: "Profile", telegramId: "Telegram ID", language: "Language", role: "User", noActivity: "No activity data has been recorded yet."
  };

  const escapeHtml = value => String(value ?? "").replace(/[&<>\"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;" }[c]));
  const headers = () => ({ "X-Telegram-Init-Data": tg?.initData || "" });
  const svg = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="${d}"/></svg>`;
  const icons = { user:"M20 21a8 8 0 0 0-16 0M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8", group:"M4 7h16v10H4zM8 7V5h8v2", channel:"M6 4h12v16H6z", shield:"M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", chart:"M4 17l5-5 4 3 7-8", back:"M15 18l-6-6 6-6", arrow:"M9 18l6-6-6-6" };
  const icon = name => svg(icons[name] || icons.chart);

  async function get(path) {
    const response = await fetch(`${API}${path}`, { headers: headers(), cache: "no-store" });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Request failed");
    return response.json();
  }

  function show(route) {
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active-page"));
    $(route === "chat" ? "chatPage" : `${route}Page`).classList.add("active-page");
    document.querySelectorAll(".nav-item").forEach(n => n.classList.toggle("active", n.dataset.route === route));
  }

  function card(chat) {
    const type = chat.type === "channel" ? t().channel : t().group;
    return `<button class="space-card" data-chat="${escapeHtml(chat.chat_id)}"><span class="space-symbol">${icon(chat.type === "channel" ? "channel" : "group")}</span><span class="space-copy"><strong>${escapeHtml(chat.title)}</strong><small>${type}</small><span class="space-meta">${chat.member_count ?? "—"} ${t().members} · ${chat.message_count ?? 0} ${t().messages}</span></span><span class="chevron">${icon("arrow")}</span></button>`;
  }

  async function home() {
    show("home");
    const el = $("homePage");
    el.innerHTML = `<div class="page-head"><div><span class="eyebrow">XAI MASTER</span><h1>${escapeHtml([user.first_name, user.last_name].filter(Boolean).join(" ") || "User")}</h1><p>${t().hint}</p></div><button class="icon-button" id="homeProfile">${icon("user")}</button></div><section class="section"><div class="section-head"><div><span class="eyebrow">WORKSPACES</span><h2>${t().managed}</h2></div><span class="count-pill">${state.groups.length}</span></div><div id="spaceList"></div></section>`;
    $("homeProfile").onclick = profile;
    const list = $("spaceList");
    if (!state.groups.length) list.innerHTML = `<div class="empty-card">${icon("shield")}<h3>${t().empty}</h3><p>${t().emptyHint}</p></div>`;
    else {
      list.innerHTML = state.groups.map(card).join("");
      list.querySelectorAll("[data-chat]").forEach(n => n.onclick = () => openChat(n.dataset.chat));
    }
  }

  async function market() {
    show("market");
    const el = $("marketPage");
    el.innerHTML = `<div class="page-head"><div><span class="eyebrow">MARKET</span><h1>${t().market}</h1><p>${t().live}</p></div><button class="outline-button" id="refreshMarket">${t().refresh}</button></div><div id="marketList" class="market-grid"><div class="loading-card">Loading...</div></div><section class="section"><div class="section-head"><div><span class="eyebrow">${t().crypto}</span><h2>24h</h2></div></div><div class="chart-panel" id="marketChart">Loading...</div></section>`;
    $("refreshMarket").onclick = market;
    try {
      const [crypto, publicData] = await Promise.all([get("/api/market/crypto"), fetch("/api/market/public", { cache: "no-store" }).then(r => r.ok ? r.json() : {})]);
      const items = crypto || [];
      const publicCards = publicData?.gold_usd ? [{ symbol:t().gold, price_usd:publicData.gold_usd, change_24h:null }] : [];
      $("marketList").innerHTML = [...publicCards, ...items.slice(0, 8)].map(x => `<article class="market-card"><div><span class="market-symbol">${escapeHtml(x.symbol)}</span><strong>${x.price_usd == null ? "—" : Number(x.price_usd).toLocaleString(undefined,{maximumFractionDigits:4})}</strong></div><span class="change">${x.change_24h == null ? "—" : `${Number(x.change_24h).toFixed(2)}%`}</span></article>`).join("");
      $("marketChart").innerHTML = lineChart(items);
    } catch (e) { $("marketList").innerHTML = `<div class="empty-card">${icon("chart")}<h3>${escapeHtml(e.message)}</h3></div>`; $("marketChart").textContent = "No data"; }
  }

  function lineChart(items) {
    if (!items.length) return t().noActivity;
    const vals = items.map(x => Number(x.change_24h || 0));
    const min = Math.min(-1, ...vals), max = Math.max(1, ...vals);
    const points = vals.map((v,i) => `${10 + i * 280 / Math.max(1, vals.length-1)},${85 - ((v-min)/(max-min))*65}`).join(" ");
    return `<svg class="chart-svg" viewBox="0 0 300 100" preserveAspectRatio="none"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg><div class="chart-labels">${items.map(x => `<span>${escapeHtml(x.symbol)}</span>`).join("")}</div>`;
  }

  function groups() {
    show("groups");
    const el = $("groupsPage");
    el.innerHTML = `<div class="page-head"><div><span class="eyebrow">WORKSPACES</span><h1>${t().groups}</h1><p>${t().hint}</p></div></div><section class="section">${state.groups.length ? state.groups.map(card).join("") : `<div class="empty-card">${icon("group")}<h3>${t().empty}</h3><p>${t().emptyHint}</p></div>`}</section>`;
    el.querySelectorAll("[data-chat]").forEach(n => n.onclick = () => openChat(n.dataset.chat));
  }

  async function openChat(chatId) {
    show("chat");
    const el = $("chatPage");
    el.innerHTML = `<button class="back-button" id="chatBack">${icon("back")} ${t().back}</button><div class="loading-card">Loading...</div>`;
    $("chatBack").onclick = home;
    try {
      const [chat, settings, stats] = await Promise.all([get(`/api/miniapp/groups/${chatId}`), get(`/api/miniapp/groups/${chatId}/settings`), get(`/api/miniapp/groups/${chatId}/stats`)]);
      state.chat = chat; state.settings = settings; state.stats = stats;
      renderChat(chatId);
    } catch (e) { el.innerHTML += `<div class="empty-card"><h3>${escapeHtml(e.message)}</h3></div>`; }
  }

  function renderChat(chatId) {
    const chat = state.chat, stats = state.stats || {};
    const rules = [
      ["anti_link",t().antiLink],["mention_lock",t().antiUsername],["hashtag_lock",t().antiHashtag],["forward_lock",t().antiForward],["anti_spam",t().antiSpam],["anti_flood",t().antiFlood],["profanity_filter",t().bannedWords],["phone_lock",t().phone],["drug_filter",t().drug],["nsfw_filter",t().nsfw],["photo_lock",t().photo],["video_lock",t().video],["document_lock",t().document],["audio_lock",t().audio],["voice_lock",t().voice],["sticker_lock",t().sticker],["animation_lock",t().animation],["poll_lock",t().poll],["location_lock",t().location],["contact_lock",t().contact]
    ];
    const bars = (stats.chart || []).map(x => `<span class="activity-bar" style="height:${Math.max(4,Number(x.messages||0)/Math.max(1,...(stats.chart||[]).map(y=>Number(y.messages||0)))*100)}%" title="${escapeHtml(x.date)}"></span>`).join("");
    const el = $("chatPage");
    el.innerHTML = `<button class="back-button" id="chatBack">${icon("back")} ${t().back}</button><section class="chat-hero"><span class="space-symbol">${icon(chat.type === "channel" ? "channel" : "group")}</span><div><span class="eyebrow">${chat.type === "channel" ? t().channel : t().group}</span><h1>${escapeHtml(chat.title)}</h1></div></section><div class="metric-grid"><div class="metric"><small>${t().members}</small><strong>${chat.member_count ?? "—"}</strong></div><div class="metric"><small>${t().messages}</small><strong>${stats.messages ?? 0}</strong></div><div class="metric"><small>${t().deleted}</small><strong>${stats.deleted ?? 0}</strong></div><div class="metric"><small>${t().warnings}</small><strong>${stats.warnings ?? 0}</strong></div></div><section class="section"><div class="section-head"><div><span class="eyebrow">${t().activity}</span><h2>${t().messages}</h2></div></div><div class="chart-panel"><div class="activity-chart">${bars || `<p class="muted">${t().noActivity}</p>`}</div></div></section><section class="section"><div class="section-head"><div><span class="eyebrow">SECURITY</span><h2>${t().security}</h2></div></div><div class="settings-list">${rules.map(([key,label]) => `<label class="setting-row"><span><strong>${label}</strong><small>${escapeHtml(key)}</small></span><input type="checkbox" data-setting="${key}" ${state.settings[key] ? "checked" : ""}><i></i></label>`).join("")}</div></section>`;
    $("chatBack").onclick = home;
    el.querySelectorAll("[data-setting]").forEach(input => input.onchange = () => updateSetting(chatId,input.dataset.setting,input.checked));
  }

  async function updateSetting(chatId, feature, enabled) {
    try {
      const response = await fetch(`/api/miniapp/groups/${chatId}/settings`, { method:"PATCH", headers:{...headers(),"Content-Type":"application/json"}, body:JSON.stringify({feature,enabled}) });
      if (!response.ok) throw new Error((await response.json().catch(()=>({}))).detail || "Unable to save setting");
      state.settings[feature] = enabled;
      tg?.HapticFeedback?.notificationOccurred?.("success");
    } catch (e) { tg?.HapticFeedback?.notificationOccurred?.("error"); alert(e.message); renderChat(chatId); }
  }

  function profile() {
    show("profile");
    const name = [user.first_name,user.last_name].filter(Boolean).join(" ") || "User";
    $("profilePage").innerHTML = `<button class="back-button" id="profileBack">${icon("back")} ${t().back}</button><section class="profile-card"><div class="profile-large">${user.photo_url ? `<img src="${escapeHtml(user.photo_url)}" alt="">` : escapeHtml(name.slice(0,1))}</div><h1>${escapeHtml(name)}</h1><p>${escapeHtml(user.username ? `@${user.username}` : "Telegram profile")}</p><div class="profile-info"><div><span>${t().telegramId}</span><strong>${escapeHtml(user.id || "—")}</strong></div><div><span>${t().language}</span><strong>${state.lang === "fa" ? "فارسی" : "English"}</strong></div><div><span>${t().role}</span><strong>${t().role}</strong></div></div></section>`;
    $("profileBack").onclick = home;
  }

  $("profileButton").onclick = profile;
  document.querySelectorAll("[data-route]").forEach(button => button.onclick = () => { const r=button.dataset.route; if(r==="home")home(); if(r==="market")market(); if(r==="groups")groups(); });
  if (user.photo_url) { $("profileImage").src=user.photo_url; $("profileImage").classList.remove("hidden"); $("profileInitial").classList.add("hidden"); }
  $("profileInitial").textContent=(user.first_name||"A").slice(0,1).toUpperCase();
  $("online").textContent=state.lang === "fa" ? "آنلاین" : "ONLINE";
  $("navHome").textContent=t().home; $("navMarket").textContent=t().market; $("navGroups").textContent=t().groups;

  (async () => { try { state.groups=(await get("/api/miniapp/groups")).groups||[]; } catch { state.groups=[]; } home(); })();
})();
