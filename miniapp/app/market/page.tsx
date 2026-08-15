import AppShell from "../components/AppShell";

export default function MarketPage() {
  return <AppShell><section className="space-y-4"><div className="rounded-3xl border border-white/10 bg-[var(--surface)] p-6"><p className="text-xs text-[var(--muted)]">XAI MASTER MARKET</p><h2 className="mt-2 text-2xl font-semibold">Market</h2><p className="mt-2 text-sm text-[var(--muted)]">Live prices, charts, watchlist and alerts.</p></div><div className="grid gap-3">{["Bitcoin","Tether","Gold","USD","EUR"].map((name) => <div key={name} className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="text-sm text-[var(--muted)]">{name}</p><p className="mt-2 text-2xl font-semibold">—</p><p className="mt-1 text-xs text-[var(--muted)]">24H —</p></div>)}</div></section></AppShell>;
}
