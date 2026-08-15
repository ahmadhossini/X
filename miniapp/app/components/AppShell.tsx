"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<{ name: string; username?: string; photo?: string }>({ name: "Telegram User" });
  const [profileOpen, setProfileOpen] = useState(false);
  const [fa, setFa] = useState(false);

  useEffect(() => {
    const tg = (window as Window & { Telegram?: { WebApp?: any } }).Telegram?.WebApp;
    tg?.ready?.(); tg?.expand?.();
    const u = tg?.initDataUnsafe?.user;
    if (u) setUser({ name: [u.first_name, u.last_name].filter(Boolean).join(" ") || "Telegram User", username: u.username, photo: u.photo_url });
    setFa(Boolean(u?.language_code?.startsWith("fa")));
  }, []);

  const nav = [{ href: "/", fa: "خانه", en: "Home" }, { href: "/market", fa: "بازار", en: "Market" }, { href: "/groups", fa: "گروه‌ها و کانال‌ها", en: "Groups & Channels" }];
  return <main dir={fa ? "rtl" : "ltr"} className="mx-auto min-h-screen max-w-md px-4 pb-28 pt-4">
    <header className="mb-5 flex items-center justify-between"><div><p className="text-xs text-[var(--muted)]">XAI MASTER</p><h1 className="text-xl font-semibold">{fa ? "مرکز مدیریت" : "Management Center"}</h1></div><button onClick={() => setProfileOpen(true)} className="rounded-full border border-white/10 bg-white/5 p-1.5">{user.photo ? <img src={user.photo} alt="" className="h-9 w-9 rounded-full object-cover" /> : <div className="h-9 w-9 rounded-full bg-white/10 text-center pt-2 text-xs">{user.name.slice(0,1)}</div>}</button></header>
    {children}
    {profileOpen && <div className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm" onClick={() => setProfileOpen(false)}><section onClick={(e) => e.stopPropagation()} className="absolute right-3 top-3 w-[calc(100%-24px)] max-w-md rounded-3xl border border-white/10 bg-[#101622]/95 p-5 shadow-2xl"><div className="flex items-center gap-4">{user.photo && <img src={user.photo} alt="" className="h-16 w-16 rounded-full object-cover" />}<div><h2 className="text-lg font-semibold">{user.name}</h2>{user.username && <p className="text-sm text-[var(--muted)]">@{user.username}</p>}</div></div></section></div>}
    <nav className="fixed bottom-3 left-1/2 z-50 flex w-[calc(100%-24px)] max-w-md -translate-x-1/2 rounded-2xl border border-white/10 bg-black/60 p-1.5 backdrop-blur-xl">{nav.map((item) => <Link key={item.href} href={item.href} className={`flex flex-1 flex-col gap-1 rounded-xl px-2 py-3 text-center text-xs ${pathname === item.href ? "bg-white/10 text-white" : "text-[var(--muted)]"}`}><span>•</span>{fa ? item.fa : item.en}</Link>)}</nav>
  </main>;
}
