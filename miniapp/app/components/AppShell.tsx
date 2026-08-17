"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

function Icon({ name }: { name: "home" | "market" | "groups" }) {
  if (name === "home") return <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5"><path d="M3 10.5 12 3l9 7.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><path d="M5.5 9.5V21h13V9.5M9 21v-6h6v6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/></svg>;
  if (name === "market") return <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5"><path d="M4 18V6M4 18h16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/><path d="m7 15 4-5 3 2 5-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/><circle cx="19" cy="6" r="1.2" fill="currentColor"/></svg>;
  return <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5"><rect x="3" y="5" width="18" height="15" rx="3" fill="none" stroke="currentColor" strokeWidth="1.7"/><path d="M8 5V3M16 5V3M7 10h10M7 14h4M13 14h4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<{ name: string; username?: string; photo?: string }>({ name: "Telegram User" });
  const [profileOpen, setProfileOpen] = useState(false);
  const [fa, setFa] = useState(false);
  useEffect(() => { const tg = (window as Window & { Telegram?: { WebApp?: any } }).Telegram?.WebApp; tg?.ready?.(); tg?.expand?.(); const u = tg?.initDataUnsafe?.user; if (u) setUser({ name: [u.first_name, u.last_name].filter(Boolean).join(" ") || "Telegram User", username: u.username, photo: u.photo_url }); setFa(Boolean(u?.language_code?.startsWith("fa"))); }, []);
  const nav = [{ href: "/", icon: "home" as const, fa: "خانه", en: "Home" }, { href: "/market", icon: "market" as const, fa: "بازار", en: "Market" }, { href: "/groups", icon: "groups" as const, fa: "گروه‌ها", en: "Groups" }];
  return <main dir={fa ? "rtl" : "ltr"} className="mx-auto min-h-screen max-w-md bg-[var(--background)] px-4 pb-28 pt-4">
    <header className="mb-6 flex items-center justify-between"><div><p className="text-[10px] font-medium uppercase tracking-[0.28em] text-[var(--muted)]">XAI MASTER</p></div><button onClick={() => setProfileOpen(true)} className="rounded-full border border-white/10 bg-white/5 p-1 transition hover:bg-white/10 active:scale-95" aria-label={fa ? "پروفایل" : "Profile"}>{user.photo ? <img src={user.photo} alt="" className="h-9 w-9 rounded-full object-cover" /> : <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-xs font-semibold">{user.name.slice(0,1)}</div>}</button></header>
    {children}
    {profileOpen && <div className="fixed inset-0 z-[60] bg-black/65 backdrop-blur-md" onClick={() => setProfileOpen(false)}><section onClick={(e) => e.stopPropagation()} className="absolute right-3 top-3 w-[calc(100%-24px)] max-w-md rounded-[28px] border border-white/10 bg-[#10151f]/95 p-5 shadow-2xl"><div className="flex items-center gap-4">{user.photo ? <img src={user.photo} alt="" className="h-16 w-16 rounded-full object-cover" /> : <div className="flex h-16 w-16 items-center justify-center rounded-full bg-white/10 text-lg font-semibold">{user.name.slice(0,1)}</div>}<div><h2 className="text-lg font-semibold">{user.name}</h2>{user.username && <p className="mt-1 text-sm text-[var(--muted)]">@{user.username}</p>}<p className="mt-1 text-xs text-[var(--muted)]">Telegram profile</p></div></div></section></div>}
    <nav className="fixed bottom-3 left-1/2 z-50 flex w-[calc(100%-24px)] max-w-md -translate-x-1/2 rounded-[22px] border border-white/10 bg-[#0b0f16]/85 p-1.5 shadow-2xl backdrop-blur-2xl">{nav.map((item) => { const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href); return <Link key={item.href} href={item.href} className={`flex flex-1 flex-col items-center justify-center gap-1 rounded-[17px] px-2 py-2.5 text-[11px] transition ${active ? "bg-white/[0.09] text-white" : "text-[var(--muted)] hover:text-white"}`}><Icon name={item.icon}/><span>{fa ? item.fa : item.en}</span></Link>; })}</nav>
  </main>;
}
