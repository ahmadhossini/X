const statusEl = document.getElementById("status");

async function loadDashboard() {
  try {
    const health = await fetch("/health");
    if (!health.ok) throw new Error("API unavailable");
    statusEl.textContent = "آنلاین";

    const response = await fetch("/api/market/crypto");
    if (!response.ok) throw new Error("Market unavailable");

    const assets = await response.json();
    for (const asset of assets) {
      const element = document.getElementById(asset.symbol.toLowerCase());
      if (element && asset.price_usd != null) {
        element.textContent = `$${Number(asset.price_usd).toLocaleString()}`;
      }
    }
  } catch (error) {
    statusEl.textContent = "خطا در اتصال";
    console.error(error);
  }
}

loadDashboard();
