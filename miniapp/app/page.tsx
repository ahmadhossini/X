"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AppShell from "./components/AppShell";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function Arrow() { return <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>; }
function ChatIcon({ channel }: { channel: boolean }) { return channel ? <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true"><path d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H11l-5 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" strokeWidth="1.6"/><path d="M8 9h8M8 12h5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg> : <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true"><circle cx="12" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.6"/><path d="M5 20c.7-3.3 3.2-5 7-5s6.3 1.7 7 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>; }

export default function HomePage() {
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { const tg = (window as Window & { Telegram?: { WebApp?: any } }).Telegram?.WebApp; fetch(`${API_BASE}/api/miniapp/groups`, { headers: { "X-Telegram-Init-Data": tg?.initData ?? "" }, cache: "no-store" }).then(async r => { if (!r.ok) throw new Error("Unable to load managed chats"); return r.json(); }).then(d => setGroups(Array.isArray(d.groups) ? d.groups : [])).catch(e => setError(e.message)).finally(() => setLoading(false)); }, []);
  const managed = groups.filter(g => ["group", "supergroup", "channel"].includes(g.type));
  return <AppShell><section className="space-y-5">
    <div className="rounded-[30px] border border-white/10 bg-gradient-to-br from-white/[0.09] to-white/[0.025] p-5 shadow-2xl"><p className="text-[10px] font-medium uppercase tracking-[0.25em] text-[var(--muted)]">XAI MASTER</p><h1 className="mt-3 text-2xl font-semibold tracking-tight">{groups.length ? "Your spaces" : "Your Telegram spaces"}</h1><p className="mt-2 max-w-[290px] text-sm leading-6 text-[var(--muted)]">Manage the groups and channels where XAI MASTER has access.</p></div>
    <div className="flex items-end justify-between"><div><p className="text-xs text-[var(--muted)]">MANAGED</p><h2 className="mt-1 text-lg font-semibold">Groups & Channels</h2></div><span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-[var(--muted)]">{managed.length}</span></div>
    {loading && <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">Loading...</div>}
    {error && <div className="rounded-2xl border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-200">{error}</div>}
    {!loading && !error && managed.length > 0 && <div className="space-y-3">{managed.map(g => <Link href={`/groups/${g.chat_id}`} key={g.chat_id} className="group block rounded-[24px] border border-white/10 bg-white/[0.045] p-4 transition hover:border-white/20 hover:bg-white/[0.07] active:scale-[0.99]"><div className="flex items-center gap-3"><div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white/[0.08] text-[var(--muted)]"><ChatIcon channel={g.type === "channel"}/></div><div className="min-w-0 flex-1"><p className="truncate font-semibold">{g.title}</p><p className="mt-1 truncate text-xs text-[var(--muted)]">{g.type === "channel" ? "Channel" : "Group"}{g.username ? ` • @${g.username}` : ""}</p></div><Arrow/></div><div className="mt-4 grid grid-cols-3 gap-2"><div className="rounded-xl bg-black/10 p-2.5"><b className="block text-sm">{g.member_count ?? "—"}</b><small className="text-[10px] text-[var(--muted)]">Members</small></div><div className="rounded-xl bg-black/10 p-2.5"><b className="block text-sm">{g.message_count ?? "—"}</b><small className="text-[10px] text-[var(--muted)]">Messages</small></div><div className="rounded-xl bg-black/10 p-2.5"><b className="block text-sm">{g.deleted_count ?? "—"}</b><small className="text-[10px] text-[var(--muted)]">Deleted</small></div></div></Link>)}</div>}
    {!loading && !error && managed.length === 0 && <div className="rounded-[24px] border border-dashed border-white/15 bg-white/[0.025] p-7 text-center"><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-[var(--muted)]"><ChatIcon channel={false}/></div><h3 className="mt-4 font-semibold">No managed chats</h3><p className="mx-auto mt-2 max-w-[280px] text-sm leading-6 text-[var(--muted)]">Add XAI MASTER as an administrator to a group or channel, then reopen the app.</p></div>}
  </section></AppShell>;
}
