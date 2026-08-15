"use client";

import { useEffect, useState } from "react";

type Tab = "home" | "market" | "groups";
type Group = { id: number; title: string; type?: string; status?: string; member_count?: number | null };

const tabs: { id: Tab; fa: string; en: string }[] = [
  { id: "home", fa: "خانه", en: "Home" },
  { id: "market", fa: "بازار", en: "Market" },
  { id: "groups", fa: "گروه‌ها و کانال‌ها", en: "Groups & Channels" },
];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function tg() {
  if (typeof window === "undefined") return undefined;
  return (window as Window & { Telegram?: { WebApp?: any } }).Telegram?.WebApp;
}

async function api(path: string, init?: RequestInit) {
  const initData = tg()?.initData ?? "";
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": initData, ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "API request failed");
  return response.json();
}

export default function MiniApp() {
  const [tab, setTab] = useState<Tab>("home");
  const [language, setLanguage] = useState<"fa" | "en">("en");
  const [user, setUser] = useState<{ name: string; username?: string; photo?: string }>({ name: "Telegram User" });
  const [groups, setGroups] = useState<Group[]>([]);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [groupsError, setGroupsError] = useState("");

  useEffect(() => {
    const webApp = tg();
    webApp?.ready?.();
    webApp?.expand?.();
    const u = webApp?.initDataUnsafe?.user;
    if (u) setUser({ name: [u.first_name, u.last_name].filter(Boolean).join(" ") || "Telegram User", username: u.username, photo: u.photo_url });
    if (webApp?.initDataUnsafe?.user?.language_code?.startsWith("fa")) setLanguage("fa");
  }, []);

  useEffect(() => {
    if (tab !== "groups") return;
    setLoadingGroups(true);
    setGroupsError("");
    api("/api/miniapp/groups")
      .then((data) => setGroups(Array.isArray(data.groups) ? data.groups : []))
      .catch((error: Error) => setGroupsError(error.message))
      .finally(() => setLoadingGroups(false));
  }, [tab]);

  const fa = language === "fa";

  return (
    <main dir={fa ? "rtl" : "ltr"} className="mx-auto min-h-screen max-w-md px-4 pb-28 pt-5">
      <header className="mb-5 flex items-center gap-3">
        {user.photo ? <img src={user.photo} alt="" className="h-12 w-12 rounded-full object-cover" /> : <div className="h-12 w-12 rounded-full border border-white/10 bg-white/5" />}
        <div><p className="text-xs text-[var(--muted)]">XAI MASTER V3</p><h1 className="text-lg font-semibold">{user.name}</h1>{user.username && <p className="text-xs text-[var(--muted)]">@{user.username}</p>}</div>
      </header>

      {tab === "home" && <Home fa={fa} />}
      {tab === "market" && <Market fa={fa} />}
      {tab === "groups" && <Groups fa={fa} groups={groups} loading={loadingGroups} error={groupsError} onRetry={() => setTab("home")} />}

      <nav className="fixed bottom-3 left-1/2 z-50 flex w-[calc(100%-24px)] max-w-md -translate-x-1/2 rounded-2xl border border-white/10 bg-black/60 p-1.5 backdrop-blur-xl">
        {tabs.map((item) => <button key={item.id} onClick={() => setTab(item.id)} className={`flex flex-1 flex-col gap-1 rounded-xl px-2 py-3 text-xs ${tab === item.id ? "bg-white/10 text-white" : "text-[var(--muted)]"}`}><span>•</span>{fa ? item.fa : item.en}</button>)}
      </nav>
    </main>
  );
}

function Home({ fa }: { fa: boolean }) {
  return <section className="space-y-4"><Card title={fa ? "مرکز مدیریت" : "Management Center"} text={fa ? "مدیریت گروه‌ها، امنیت و امکانات XAI MASTER از یک پنل." : "Manage groups, security and XAI MASTER features from one panel."} /><div className="grid grid-cols-2 gap-3"><Stat title={fa ? "گروه‌های فعال" : "Active Groups"} value="—" /><Stat title={fa ? "پیام حذف‌شده" : "Deleted Messages"} value="—" /><Stat title={fa ? "اسپم شناسایی‌شده" : "Spam Detected"} value="—" /><Stat title={fa ? "کاربر محدودشده" : "Restricted Users"} value="—" /></div></section>;
}

function Market({ fa }: { fa: boolean }) {
  return <section className="space-y-4"><Card title={fa ? "بازار" : "Market"} text={fa ? "قیمت‌ها از Backend دریافت می‌شوند؛ کلید API در Frontend قرار نمی‌گیرد." : "Prices are served by the backend; API secrets never live in the frontend."} /><div className="space-y-3"><Stat title="Bitcoin" value="—" /><Stat title="Tether" value="—" /><Stat title={fa ? "طلا" : "Gold"} value="—" /><Stat title={fa ? "دلار" : "USD"} value="—" /></div></section>;
}

function Groups({ fa, groups, loading, error }: { fa: boolean; groups: Group[]; loading: boolean; error: string; onRetry: () => void }) {
  return <section className="space-y-4"><Card title={fa ? "گروه‌ها و کانال‌ها" : "Groups & Channels"} text={fa ? "این فهرست مستقیماً از Backend احراز‌شده دریافت می‌شود." : "This list is loaded directly from the authenticated backend."} />
    {loading && <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">{fa ? "در حال دریافت..." : "Loading..."}</div>}
    {!loading && error && <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-red-300">{error}</div>}
    {!loading && !error && groups.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">{fa ? "هنوز گروه مدیریتی برای این حساب دریافت نشده است." : "No managed groups are available for this account yet."}</div>}
    {!loading && groups.map((group) => <div key={group.id} className="rounded-2xl border border-white/10 bg-white/5 p-4"><div className="flex items-center justify-between"><div><p className="font-semibold">{group.title}</p><p className="mt-1 text-xs text-[var(--muted)]">{group.type ?? "chat"}{group.member_count ? ` • ${group.member_count}` : ""}</p></div><span className="text-xs text-[var(--muted)]">• {group.status ?? "active"}</span></div></div>)}
  </section>;
}

function Card({ title, text }: { title: string; text: string }) { return <div className="rounded-3xl border border-white/10 bg-[var(--surface)] p-5 shadow-2xl backdrop-blur-xl"><h2 className="mb-2 text-base font-semibold">{title}</h2><p className="text-sm leading-6 text-[var(--muted)]">{text}</p></div>; }
function Stat({ title, value }: { title: string; value: string }) { return <div className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-[var(--muted)]">{title}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>; }
