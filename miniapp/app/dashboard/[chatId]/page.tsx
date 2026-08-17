"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const icon = (d: string) => <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d={d}/></svg>;

const RULES = [
  ["anti_link", "Anti Link", "Remove unauthorized links"],
  ["mention_lock", "Anti Username", "Remove Telegram usernames such as @user"],
  ["hashtag_lock", "Anti Hashtag", "Remove hashtags such as #crypto"],
  ["forward_lock", "Anti Forward", "Remove forwarded messages"],
  ["anti_spam", "Anti Spam", "Remove repeated messages and repeated advertising"],
  ["anti_flood", "Anti Flood", "Mute users who exceed the message rate"],
  ["profanity_filter", "Banned Words", "Filter configured inappropriate terms"],
  ["photo_lock", "Photo Lock", "Remove photos when enabled"],
  ["video_lock", "Video Lock", "Remove videos when enabled"],
  ["document_lock", "File Lock", "Remove documents and files when enabled"],
  ["audio_lock", "Audio Lock", "Remove music/audio when enabled"],
  ["voice_lock", "Voice Lock", "Remove voice messages when enabled"],
  ["sticker_lock", "Sticker Lock", "Remove stickers when enabled"],
  ["animation_lock", "GIF Lock", "Remove GIF and animation messages"],
  ["poll_lock", "Poll Lock", "Remove polls when enabled"],
  ["location_lock", "Location Lock", "Remove location messages"],
  ["contact_lock", "Contact Lock", "Remove contact messages"],
  ["phone_lock", "Phone Filter", "Remove phone numbers"],
  ["drug_filter", "Drug Filter", "Remove configured drug-related terms"],
  ["nsfw_filter", "Content Filter", "Remove configured explicit terms"],
] as const;

export default function DashboardPage() {
  const { chatId } = useParams<{ chatId: string }>();
  const router = useRouter();
  const [chat, setChat] = useState<any>(null);
  const [settings, setSettings] = useState<Record<string, boolean>>({});
  const [stats, setStats] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function telegram() {
    return typeof window !== "undefined" ? (window as any).Telegram?.WebApp : undefined;
  }

  useEffect(() => {
    const tg = telegram();
    tg?.ready?.();
    tg?.expand?.();
    const headers = { "X-Telegram-Init-Data": tg?.initData ?? "" };
    Promise.all([
      fetch(`${API}/api/miniapp/groups/${chatId}`, { headers }).then(r => r.ok ? r.json() : Promise.reject(new Error("Access denied"))),
      fetch(`${API}/api/miniapp/groups/${chatId}/settings`, { headers }).then(r => r.ok ? r.json() : Promise.reject(new Error("Settings unavailable"))),
      fetch(`${API}/api/miniapp/groups/${chatId}/stats`, { headers }).then(r => r.ok ? r.json() : {}),
    ]).then(([c, s, st]) => {
      setChat(c);
      setSettings(s ?? {});
      setStats(st ?? {});
    }).catch(e => setError(e.message || "Unable to load dashboard")).finally(() => setLoading(false));
  }, [chatId]);

  async function toggle(feature: string, enabled: boolean) {
    const previous = settings[feature];
    setSaving(feature);
    setNotice("");
    setSettings(current => ({ ...current, [feature]: enabled }));
    try {
      const tg = telegram();
      const response = await fetch(`${API}/api/miniapp/groups/${chatId}/settings`, {
        method: "PATCH",
        headers: { "X-Telegram-Init-Data": tg?.initData ?? "", "Content-Type": "application/json" },
        body: JSON.stringify({ feature, enabled }),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to save setting");
      setNotice("Setting saved");
    } catch (e: any) {
      setSettings(current => ({ ...current, [feature]: previous }));
      setNotice(e.message || "Unable to save setting");
    } finally {
      setSaving(null);
    }
  }

  const chart = useMemo(() => Array.isArray(stats.chart) ? stats.chart : [], [stats.chart]);
  const maxMessages = Math.max(1, ...chart.map((d: any) => Number(d.messages || 0)));

  if (loading) return <Shell><div className="panel p-6 muted">Loading dashboard...</div></Shell>;
  if (error) return <Shell><div className="panel p-6 text-red-300">{error}</div></Shell>;

  return <Shell>
    <div className="space-y-4 pb-24">
      <button onClick={() => router.back()} className="muted flex items-center gap-2">{icon("M15 18l-6-6 6-6")} Back</button>

      <section className="panel p-5">
        <p className="label">GROUP / CHANNEL</p>
        <div className="mt-3 flex items-center gap-3">
          <div className="avatar">{(chat?.title ?? "X").slice(0, 1)}</div>
          <div><h1 className="text-2xl font-semibold">{chat?.title ?? `Chat ${chatId}`}</h1><p className="muted mt-1">{chat?.type ?? "Telegram chat"}</p></div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3">
        {[["Members", chat?.member_count ?? "—"], ["Messages", stats.messages ?? "—"], ["Deleted", stats.deleted ?? "—"], ["Warnings", stats.warnings ?? "—"]].map(([label, value]) => <div className="metric" key={String(label)}><span className="muted text-xs">{label}</span><strong>{String(value)}</strong></div>)}
      </div>

      <section className="panel p-5">
        <div className="flex items-center justify-between"><div><p className="label">ACTIVITY</p><h2 className="mt-1 font-semibold">Messages over the last 14 days</h2></div><span className="muted text-xs">Live data</span></div>
        {chart.length ? <div className="mt-5 flex h-32 items-end gap-1">{chart.map((point: any) => <div key={point.date} className="group flex h-full flex-1 items-end" title={`${point.date}: ${point.messages ?? 0}`}><div className="w-full rounded-t bg-cyan-400/70 transition-all" style={{ height: `${Math.max(4, (Number(point.messages || 0) / maxMessages) * 100)}%` }} /></div>)}</div> : <p className="muted mt-6">No activity data has been recorded yet.</p>}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">Security</h2><span className="muted text-xs">Changes apply to this chat</span></div>
        <div className="space-y-2">{RULES.map(([feature, title, description]) => <label className="setting" key={feature}>
          <span><b>{title}</b><small>{description}</small></span>
          <input type="checkbox" checked={Boolean(settings[feature])} disabled={saving === feature} onChange={e => toggle(feature, e.target.checked)} />
        </label>)}</div>
        {notice && <p className="muted mt-3 text-xs">{notice}</p>}
      </section>
    </div>
  </Shell>;
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="app"><header className="top"><div><span className="brand">XAI MASTER</span><h1>Dashboard</h1></div><div className="avatar">X</div></header>{children}</main>;
}
