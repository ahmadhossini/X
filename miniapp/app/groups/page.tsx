"use client";

import { useEffect, useState } from "react";
import AppShell from "../components/AppShell";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export default function GroupsPage() {
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const tg = (window as Window & { Telegram?: { WebApp?: any } }).Telegram?.WebApp;
    tg?.ready?.();
    fetch(`${API_BASE}/api/miniapp/groups`, { headers: { "X-Telegram-Init-Data": tg?.initData ?? "" }, cache: "no-store" })
      .then(async r => { if (!r.ok) throw new Error("Unable to load groups"); return r.json(); })
      .then(d => setGroups(d.groups ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  return <AppShell><section className="space-y-4"><div className="rounded-3xl border border-white/10 bg-[var(--surface)] p-6"><p className="text-xs text-[var(--muted)]">XAI MASTER</p><h2 className="mt-2 text-2xl font-semibold">Groups & Channels</h2><p className="mt-2 text-sm text-[var(--muted)]">Only chats where your Telegram account has management access appear here.</p></div>{loading && <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">Loading...</div>}{error && <div className="rounded-2xl border border-red-400/20 bg-red-400/10 p-5 text-sm">{error}</div>}{!loading && !error && groups.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">No managed groups or channels found.</div>}{groups.map(g => <button key={g.id} className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/5 p-4 text-left"><div><p className="font-semibold">{g.title}</p><p className="mt-1 text-xs text-[var(--muted)]">{g.type ?? "chat"}</p></div><span className="text-xs text-[var(--muted)]">• Manage</span></button>)}</section></AppShell>;
}
