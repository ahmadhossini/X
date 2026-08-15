"use client";

import { useEffect, useState } from "react";

type Tab = "home" | "market" | "groups";

const tabs: { id: Tab; fa: string; en: string }[] = [
  { id: "home", fa: "خانه", en: "Home" },
  { id: "market", fa: "بازار", en: "Market" },
  { id: "groups", fa: "گروه‌ها و کانال‌ها", en: "Groups & Channels" },
];

export default function MiniApp() {
  const [tab, setTab] = useState<Tab>("home");
  const [language, setLanguage] = useState<"fa" | "en">("en");
  const [user, setUser] = useState<{ name: string; username?: string; photo?: string }>({ name: "Telegram User" });

  useEffect(() => {
    const tg = (window as Window & { Telegram?: { WebApp?: { initDataUnsafe?: { user?: { first_name?: string; last_name?: string; username?: string; photo_url?: string }; language_code?: string }; ready?: () => void; expand?: () => void } } }).Telegram?.WebApp;
    tg?.ready?.();
    tg?.expand?.();
    const u = tg?.initDataUnsafe?.user;
    if (u) setUser({ name: [u.first_name, u.last_name].filter(Boolean).join(" ") || "Telegram User", username: u.username, photo: u.photo_url });
    if (tg?.initDataUnsafe?.language_code?.startsWith("fa")) setLanguage("fa");
  }, []);

  const fa = language === "fa";

  return (
    <main dir={fa ? "rtl" : "ltr"} className="mx-auto min-h-screen max-w-md px-4 pb-28 pt-5">
      <header className="mb-5 flex items-center gap-3">
        {user.photo ? <img src={user.photo} alt="" className="h-12 w-12 rounded-full object-cover" /> : <div className="h-12 w-12 rounded-full border border-white/10 bg-white/5" />}
        <div>
          <p className="text-xs text-[var(--muted)]">XAI MASTER V3</p>
          <h1 className="text-lg font-semibold">{user.name}</h1>
          {user.username && <p className="text-xs text-[var(--muted)]">@{user.username}</p>}
        </div>
      </header>

      {tab === "home" && <Home fa={fa} />}
      {tab === "market" && <Market fa={fa} />}
      {tab === "groups" && <Groups fa={fa} />}

      <nav className="fixed bottom-3 left-1/2 z-50 flex w-[calc(100%-24px)] max-w-md -translate-x-1/2 rounded-2xl border border-white/10 bg-black/60 p-1.5 backdrop-blur-xl">
        {tabs.map((item) => <button key={item.id} onClick={() => setTab(item.id)} className={`flex flex-1 flex-col gap-1 rounded-xl px-2 py-3 text-xs ${tab === item.id ? "bg-white/10 text-white" : "text-[var(--muted)]"}`}><span>•</span>{fa ? item.fa : item.en}</button>)}
      </nav>
    </main>
  );
}

function Home({ fa }: { fa: boolean }) {
  return <section className="space-y-4">
    <Card title={fa ? "مرکز مدیریت" : "Management Center"} text={fa ? "مدیریت گروه‌ها، امنیت و امکانات XAI MASTER از یک پنل." : "Manage groups, security and XAI MASTER features from one panel."} />
    <div className="grid grid-cols-2 gap-3"><Stat title={fa ? "گروه‌های فعال" : "Active Groups"} value="—" /><Stat title={fa ? "پیام حذف‌شده" : "Deleted Messages"} value="—" /><Stat title={fa ? "اسپم شناسایی‌شده" : "Spam Detected"} value="—" /><Stat title={fa ? "کاربر محدودشده" : "Restricted Users"} value="—" /></div>
  </section>;
}

function Market({ fa }: { fa: boolean }) {
  return <section className="space-y-4"><Card title={fa ? "بازار" : "Market"} text={fa ? "قیمت‌ها از Backend دریافت خواهند شد؛ کلید API هرگز در Frontend قرار نمی‌گیرد." : "Prices will be served by the backend; API secrets never live in the frontend."} />
    <div className="space-y-3"><Stat title="Bitcoin" value="—" /><Stat title="Tether" value="—" /><Stat title={fa ? "طلا" : "Gold"} value="—" /><Stat title={fa ? "دلار" : "USD"} value="—" /></div></section>;
}

function Groups({ fa }: { fa: boolean }) {
  return <section className="space-y-4"><Card title={fa ? "گروه‌ها و کانال‌ها" : "Groups & Channels"} text={fa ? "فقط گروه‌هایی که ربات در آن‌ها دسترسی مدیریت دارد در اینجا نمایش داده می‌شوند." : "Only chats where the bot has management access will appear here."} />
    <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-[var(--muted)]">{fa ? "هنوز گروهی برای این کاربر دریافت نشده است." : "No managed groups have been loaded yet."}</div></section>;
}

function Card({ title, text }: { title: string; text: string }) { return <div className="rounded-3xl border border-white/10 bg-[var(--surface)] p-5 shadow-2xl backdrop-blur-xl"><h2 className="mb-2 text-base font-semibold">{title}</h2><p className="text-sm leading-6 text-[var(--muted)]">{text}</p></div>; }
function Stat({ title, value }: { title: string; value: string }) { return <div className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="text-xs text-[var(--muted)]">{title}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>; }
