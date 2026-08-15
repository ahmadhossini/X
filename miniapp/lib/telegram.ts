export type TelegramUser = { id: number; first_name: string; last_name?: string; username?: string; photo_url?: string; language_code?: string };

export function getTelegramWebApp() {
  if (typeof window === "undefined") return undefined;
  return (window as Window & { Telegram?: { WebApp?: any } }).Telegram?.WebApp;
}

export function getTelegramInitData(): string {
  return getTelegramWebApp()?.initData ?? "";
}
