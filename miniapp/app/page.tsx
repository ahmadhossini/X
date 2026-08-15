"use client";

import { useEffect, useState } from "react";

type Tab = "home" | "market" | "groups";
type Group = { id: number; title: string; type?: string; status?: string; member_count?: number | null; username?: string };

const tabs: { id: Tab; fa: string; en: string }[] = [
  { id: "home", fa: "خانه", en: "Home" },
  { id: "market", fa: "بازار", en: "Market" },
  { id: "groups", fa: "گروه‌ها و کانال‌ها", en: "Groups & Channels" },
];
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function tg() { if (typeof window === "undefined") return undefined; return (window as Window & { Telegram?: { WebApp?: any } }).Telegram?.WebApp; }
async function api(path: string) { const response = await fetch(`${API_BASE}${path}`, { headers: { "X-Telegram-Init-Data": tg()?.initData ?? "" }, cache: "no-store" }); if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "API request failed"); return response.json(); }

export default function MiniApp() {
  const [tab, setTab] = useState<Tab>("home");
  const [language, setLanguage] = useState<"fa" | "en">("en");
  const [profileOpen, setProfileOpen] = useState(false);
  const [user, setUser] = useState<{ name: string; username?: string; photo?: string }>({ name: "Telegram User" });
  const [groups, setGroups] = useState<Group[]>([]);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [groupsError, setGroupsError] = useState("");

  useEffect(() => { const webApp = tg(); webApp?.ready?.(); webApp?.expand?.(); const u = webApp?.initDataUnsafe?.user; if (u) setUser({ name: [u.first_name, u.last_name].filter(Boolean).join(" ") || "Telegram User", username: u.username, photo: u.photo_url }); if (u?.language_code?.startsWith("fa")) setLanguage("fa"); }, []);
  useEffect(() => { if (tab !== "home" && tab !== "groups") return; setLoadingGroups(true); setGroupsError(""); api("/api/miniapp/groups").then((data) => setGroups(Array.isArray(data.groups) ? data.groups : [])).catch((error: Error) => setGroupsError(error.message)).finally(() => setLoadingGroups(false)); }, [tab]);

  const fa = language === "fa";
  return <main dir={fa ? "rtl" : "ltr"} className="mx-auto min-h-screen max-w-md px-4 pb-28 pt-4">
    <header className="mb-5 flex items-center justify-between">
      <div><p className="text-xs text-[var(--muted)]">XAI MASTER</p><h1 className="text-xl font-semibold">{fa ? "مرکز مدیریت" : "Management Center"}</h1></div>
      <button onClick={() => setProfileOpen(true)} className="rounded-full border border-white/10 bg-white/5 p-1.5 transition active:scale-95" aria-label="Profile">{user.photo ? <img src={user.photo} alt="" className="h-9 w-9 rounded-full object-cover" /> : <div className="h-9 w-9 rounded-full bg-white/10 text-center pt-2 text-xs">{user.name.slice(0, 1)}</div>}</button>
    </header>

    {tab === "home" && <Home fa={fa} groups={groups} loading={loadingGroups} error={groupsError} onOpenGroups={() => setTab("groups")} />}
    {tab === "market" && <Market fa={fa} />}
    {tab === "groups" && <Groups fa={fa} groups={groups} loading={loadingGroups} error={groupsError} />}

    {profileOpen && <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm" onClick={() => setProfileOpen(false)}><section onClick={(e) => e.stopPropagation()} className="absolute right-3 top-3 w-[calc(100%-24px)] max-w-md rounded-3xl border border-white/10 bg-[#101622]/95 p-5 shadow-2xl"><div className="flex items-center gap-4">{user.photo ? <img src={user.photo} alt="" className="h-16 w-16 rounded-full object-cover" /> : <div className="h-16 w-16 rounded-full bg-white/10 text-center pt-5">{user.name.slice(0, 1)}</div>}<div><h2 className="text-lg font-semibold">{user.name}</h2>{user.username && <p className="text-sm text-[var(--muted)]">@{user.username}</p>}<p className="mt-1 text-xs text-[var(--muted)]">Telegram profile</p></div></div><button onClick={() => setProfileOpen(false)} className="mt-5 w-full rounded-xl border border-white/10 py-3 text-sm">• {fa ? "بستن" : "Close"}</button></section></div>}

    <nav className="fixed bottom-3 left-1/2 z-50 flex w-[calc(100%-24px)] max-w-md -translate-x-1/2 rounded-2xl border border-white/10 bg-black/60 p-1.5 backdrop-blur-xl">{tabs.map((item) => <button key={item.id} onClick={() => setTab(item.id)} className={`flex flex-1 flex-col gap-1 rounded-xl px-2 py-3 text-xs ${tab === item.id ? "bg-white/10 text-white" : "text-[var(--muted)]"}`}><span>•</span>{fa ? item.fa : item.en}</button>)}</nav>
  </main>;
}

function Home({ fa, groups, loading, error, onOpenGroups }: { fa: boolean; groups: Group[]; loading: boolean; error: string; onOpenGroups: () => void }) { return <section className="space-y-4"><Card title={fa ? "گروه‌ها و کانال‌های شما" : "Your Groups & Channels"} text={fa ? "گروه‌ها و کانال‌هایی که XAIMASTER در آن‌ها دسترسی مدیریتی دارد." : "Groups and channels where XAIMASTER has management access."} />{loading && <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-[var(--muted)]">{fa ? "در حال دریافت..." : "Loading..."}</div>}{!loading && error && <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-red-300">{error}</div>}{!loading && !error && groups.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">{fa ? "هنوز گروه یا کانالی پیدا نشد." : "No managed groups or channels found yet."}</div>}{!loading && groups.slice(0, 6).map((group) => <button key={group.id} onClick={onOpenGroups} className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/5 p-4 text-left"><div><p className="font-semibold">{group.title}</p><p className="mt-1 text-xs text-[var(--muted)]">{group.type ?? "chat"}{group.member_count ? ` • ${group.member_count}` : ""}</p></div><span className="text-xs text-[var(--muted)]">• {fa ? "مدیریت" : "Manage"}</span></button>)}<div className="grid grid-cols-2 gap-3"><Stat title={fa ? "گروه‌های فعال" : "Active Groups"} value={groups.length ? String(groups.length) : "—"} /><Stat title={fa ? "وضعیت امنیت" : "Security"} value="• ON" /></div></section>; }
function Market({ fa }: { fa: boolean }) { return <section className="space-y-4"><Card title={fa ? "بازار" : "Market"} text={fa ? "قیمت‌های زنده از Backend دریافت می‌شوند." : "Live prices are served by the backend."} /><Stat title="Bitcoin" value="—" /><Stat title="Tether" value="—" /><Stat title={fa ? "طلا" : "Gold"} value="—" /><Stat title={fa ? "دلار" : "USD"} value="—" /></section>; }
function Groups({ fa, groups, loading, error }: { fa: boolean; groups: Group[]; loading: boolean; error: string }) { return <section className="space-y-4"><Card title={fa ? "گروه‌ها و کانال‌ها" : "Groups & Channels"} text={fa ? "فقط چت‌هایی که دسترسی مدیریتی دارید نمایش داده می‌شوند." : "Only chats where you have management access are shown."} />{loading && <div className="text-sm text-[var(--muted)]">Loading...</div>}{error && <div className="text-sm text-red-300">{error}</div>}{!loading && !error && groups.map((group) => <div key={group.id} className="rounded-2xl border border-white/10 bg-white/5 p-4"><div className="flex items-center justify-between"><div><p className="font-semibold">{group.title}</p><p className="mt-1 text-xs text-[var(--muted)]">{group.type ?? "chat"}{group.member_count ? ` • ${group.member_count}` : ""}</p></div><span className="text-xs text-[var(--muted)]">• {fa ? "فعال" : "Active"}</span></div></div>)}</section>; }
function Card({ title, text }: { title: string; text: string }) { return <div className="rounded-3xl border border-white/10 bg-[var(--surface)] p-5 shadow-2xl backdrop-blur-xl"><h2 className="mb-2 text-base font-semibold">{title}</h2><p className="text-sm leading-6 text-[var(--muted)]">{text}</p></div>; }
function Stat({ title, value }: { title: string; value: string }) { return <div className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-[var(--muted)]">{title}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>; }
