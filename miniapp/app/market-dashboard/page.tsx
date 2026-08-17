"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
export default function MarketDashboard() {
  const [data, setData] = useState<any>({});
  const [coins, setCoins] = useState<any[]>([]);
  const [selected, setSelected] = useState("bitcoin");
  const [history, setHistory] = useState<number[]>([]);
  useEffect(() => { fetch(`${API}/api/market/public`).then(r => r.json()).then(setData).catch(() => {}); fetch(`${API}/api/market/crypto`).then(r => r.json()).then(x => setCoins(Array.isArray(x) ? x : [])).catch(() => {}); }, []);
  useEffect(() => { fetch(`${API}/api/market/crypto/${selected}/history`).then(r => r.json()).then(x => setHistory(x.prices ?? [])).catch(() => setHistory([])); }, [selected]);
  const points = history.length > 1 ? history.map((v,i)=>`${i/(history.length-1)*100},${92-(v-(Math.min(...history)))/(Math.max(...history)-Math.min(...history)||1)*78}`).join(" ") : "";
  return <main className="app market-app"><header className="top"><div><span className="brand">XAI MASTER</span><h1>Market</h1></div><span className="status">LIVE</span></header><section className="market-hero"><span>Market overview</span><strong>Live prices</strong><small>Crypto, gold and foreign exchange</small></section><div className="market-grid"><Metric label="Gold / USD" value={data.gold_usd}/><Metric label="USD / EUR" value={data.usd_eur}/><Metric label="USD / IRR" value={data.usd_irr}/></div><section className="chart-card"><div className="chart-head"><div><span className="label">PRICE HISTORY</span><h2>{coins.find(c=>c.id===selected)?.symbol ?? "BTC"}</h2></div><div className="pills"><button>24H</button><button>7D</button><button>30D</button></div></div><svg viewBox="0 0 100 100" preserveAspectRatio="none" className="chart">{points && <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.8" vectorEffect="non-scaling-stroke"/>}</svg></section><section><div className="section-title"><h2>Digital assets</h2><span>Live</span></div><div className="asset-list">{coins.map(c=><button className="asset" key={c.symbol} onClick={()=>setSelected(c.id)}><span><b>{c.symbol}</b><small>${c.price_usd ?? "—"}</small></span><strong className={c.change_24h >= 0 ? "up":"down"}>{Number(c.change_24h ?? 0).toFixed(2)}%</strong></button>)}</div></section><Bottom /></main>;
}
function Metric({label,value}:{label:string,value:any}){return <div className="metric market-metric"><span>{label}</span><strong>{value ?? "—"}</strong></div>}
function Bottom(){return <nav className="bottom"><a href="/">Home</a><a className="active" href="/market-dashboard">Market</a><a href="/groups">Groups</a></nav>}
