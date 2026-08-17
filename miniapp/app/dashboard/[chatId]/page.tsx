"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const icon = (d: string) => <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8"><path d={d}/></svg>;

export default function DashboardPage() {
  const { chatId } = useParams<{ chatId: string }>();
  const router = useRouter();
  const [chat, setChat] = useState<any>(null);
  const [settings, setSettings] = useState<any>({});
  const [stats, setStats] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const tg = typeof window !== "undefined" ? (window as any).Telegram?.WebApp : undefined;
  const headers = { "X-Telegram-Init-Data": tg?.initData ?? "" };

  useEffect(() => {
    tg?.ready?.(); tg?.expand?.();
    Promise.all([
      fetch(`${API}/api/miniapp/groups/${chatId}`, { headers }).then(r => r.ok ? r.json() : Promise.reject(new Error("Access denied"))),
      fetch(`${API}/api/miniapp/groups/${chatId}/settings`, { headers }).then(r => r.ok ? r.json() : Promise.reject(new Error("Settings unavailable"))),
      fetch(`${API}/api/miniapp/groups/${chatId}/stats`, { headers }).then(r => r.ok ? r.json() : {}).catch(() => ({})),
    ]).then(([c, s, st]) => { setChat(c); setSettings(s.settings ?? s ?? {}); setStats(st ?? {}); }).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, [chatId]);

  async function toggle(key: string, value: boolean) {
    setSettings((x: any) => ({ ...x, [key]: value }));
    await fetch(`${API}/api/miniapp/groups/${chatId}/settings`, { method: "PUT", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify({ [key]: value }) });
  }

  const rules = [
    ["anti_link", "Anti Link", "Remove unauthorized links"], ["anti_username", "Anti Username", "Block @usernames"], ["anti_hashtag", "Anti Hashtag", "Block #hashtags"], ["anti_forward", "Anti Forward", "Remove forwarded messages"], ["anti_spam", "Anti Spam", "Detect repeated advertising"], ["anti_flood", "Anti Flood", "Limit rapid messages"], ["banned_words", "Banned Words", "Filter configured words"], ["media_lock", "Media Lock", "Restrict selected media"],
  ];

  if (loading) return <Shell><div className="panel p-6">Loading dashboard...</div></Shell>;
  if (error) return <Shell><div className="panel p-6 text-red-300">{error}</div></Shell>;
  return <Shell><div className="space-y-4">
    <button onClick={() => router.back()} className="muted flex items-center gap-2">{icon("M15 18l-6-6 6-6")} Back</button>
    <section className="panel p-5"><p className="label">GROUP DASHBOARD</p><h1 className="mt-2 text-2xl font-semibold">{chat?.title ?? `Chat ${chatId}`}</h1><p className="muted mt-1">{chat?.type ?? "Telegram chat"}</p></section>
    <div className="grid grid-cols-2 gap-3">{[["Members", stats.member_count ?? chat?.member_count ?? "—"],["Messages",stats.message_count ?? "—"],["Deleted",stats.deleted_count ?? "—"],["Warnings",stats.warning_count ?? "—"]].map(([a,b])=><div className="metric" key={String(a)}><span className="muted text-xs">{a}</span><strong>{String(b)}</strong></div>)}</div>
    <section className="panel p-5"><div className="flex items-center justify-between"><div><p className="label">ACTIVITY</p><h2 className="mt-1 font-semibold">Growth</h2></div><span className="muted text-xs">14 days</span></div><svg viewBox="0 0 320 100" className="mt-5 h-32 w-full text-cyan-300"><path d="M0 78 C35 72 38 54 72 61 S110 75 138 48 S180 56 207 36 S245 42 270 24 S300 30 320 12" fill="none" stroke="currentColor" strokeWidth="3"/><path d="M0 78 C35 72 38 54 72 61 S110 75 138 48 S180 56 207 36 S245 42 270 24 S300 30 320 12 L320 100 L0 100Z" fill="currentColor" opacity=".07"/></svg></section>
    <section><div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">Security</h2><span className="muted text-xs">Live controls</span></div><div className="space-y-2">{rules.map(([key,title,description])=><label className="setting" key={key}><span><b>{title}</b><small>{description}</small></span><input type="checkbox" checked={Boolean(settings[key])} onChange={e => toggle(String(key), e.target.checked)}/></label>)}</div></section>
  </div></Shell>;
}

function Shell({ children }: { children: React.ReactNode }) { return <main className="app"><header className="top"><div><span className="brand">XAI MASTER</span><h1>Dashboard</h1></div><div className="avatar">X</div></header>{children}</main>; }
