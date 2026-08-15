"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AppShell from "./components/AppShell";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export default function HomePage() {
  const [groups, setGroups] = useState<any[]>([]);
  useEffect(() => {
    const tg = (window as Window & { Telegram?: { WebApp?: any } }).Telegram?.WebApp;
    fetch(`${API_BASE}/api/miniapp/groups`, { headers: { "X-Telegram-Init-Data": tg?.initData ?? "" }, cache: "no-store" })
      .then(r => r.ok ? r.json() : { groups: [] }).then(d => setGroups(d.groups ?? [])).catch(() => setGroups([]));
  }, []);
  return <AppShell><section className="space-y-4"><div className="rounded-3xl border border-white/10 bg-[var(--surface)] p-6"><p className="text-xs text-[var(--muted)]">XAI MASTER</p><h2 className="mt-2 text-2xl font-semibold">Home</h2><p className="mt-2 text-sm text-[var(--muted)]">Your managed Telegram groups and channels.</p></div><div className="space-y-3">{groups.length ? groups.map(g => <Link href="/groups" key={g.id} className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 p-4"><div><p className="font-semibold">{g.title}</p><p className="mt-1 text-xs text-[var(--muted)]">{g.type ?? "chat"}</p></div><span className="text-xs text-[var(--muted)]">• Manage</span></Link>) : <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">No managed groups or channels found yet.</div>}</div><div className="grid grid-cols-2 gap-3"><Link href="/market" className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-[var(--muted)]">Market</p><p className="mt-2 font-semibold">Live prices</p></Link><Link href="/groups" className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-[var(--muted)]">Groups</p><p className="mt-2 font-semibold">Manage chats</p></Link></div></section></AppShell>;
}
