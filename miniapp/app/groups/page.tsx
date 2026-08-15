"use client";

import { useEffect, useState } from "react";
import { api, type ManagedChat } from "../../lib/api";

const features = [
  ["anti_spam", "Anti Spam"], ["anti_flood", "Anti Flood"], ["anti_link", "Anti Link"],
  ["media_lock", "Media Lock"], ["forward_lock", "Forward Lock"], ["mention_lock", "Mention Lock"],
  ["hashtag_lock", "Hashtag Lock"], ["phone_lock", "Phone Lock"], ["profanity_filter", "Banned Words"],
  ["drug_filter", "Drug Filter"], ["nsfw_filter", "NSFW Filter"], ["force_join", "Force Join"],
];

export default function GroupsPage() {
  const [groups, setGroups] = useState<ManagedChat[]>([]);
  const [selected, setSelected] = useState<ManagedChat | null>(null);
  const [settings, setSettings] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");

  useEffect(() => { api.groups().then((r) => setGroups(r.groups)).catch(() => setError("Unable to load groups")); }, []);
  useEffect(() => { if (selected) api.settings(selected.id).then(setSettings).catch(() => setError("Unable to load settings")); }, [selected]);

  async function toggle(feature: string) {
    if (!selected) return;
    const next = !settings[feature];
    try {
      const updated = await api.setSetting(selected.id, feature, next);
      setSettings(updated);
    } catch { setError("Unable to save setting"); }
  }

  return <main className="mx-auto min-h-screen max-w-md space-y-4 p-4 pb-10">
    <h1 className="text-xl font-semibold">Groups & Channels</h1>
    {error && <div className="rounded-xl border border-red-400/20 bg-red-400/10 p-3 text-sm">{error}</div>}
    {!selected && groups.map((chat) => <button key={chat.id} onClick={() => setSelected(chat)} className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/5 p-4 text-left"><span><b>{chat.title}</b><small className="mt-1 block text-[var(--muted)]">{chat.type}</small></span><span>•</span></button>)}
    {!selected && groups.length === 0 && !error && <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">No managed groups found.</div>}
    {selected && <section className="space-y-3">
      <button onClick={() => setSelected(null)} className="text-sm text-[var(--muted)]">• Back</button>
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4"><h2 className="font-semibold">{selected.title}</h2><p className="text-xs text-[var(--muted)]">{selected.type}</p></div>
      {features.map(([key, label]) => <button key={key} onClick={() => toggle(key)} className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/5 p-4"><span className="text-sm">{label}</span><span className={settings[key] ? "text-[var(--accent)]" : "text-[var(--muted)]"}>{settings[key] ? "• ON" : "• OFF"}</span></button>)}
    </section>}
  </main>;
}
