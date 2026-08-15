import { getTelegramInitData } from "./telegram";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-Telegram-Init-Data", getTelegramInitData());
  headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json() as Promise<T>;
}

export type ManagedChat = { id: number; title: string; type: string; username?: string; is_admin: boolean };

export const api = {
  groups: () => request<{ groups: ManagedChat[] }>("/api/miniapp/groups"),
  settings: (chatId: number) => request<Record<string, boolean>>(`/api/miniapp/groups/${chatId}/settings`),
  setSetting: (chatId: number, feature: string, enabled: boolean) => request<Record<string, boolean>>(`/api/miniapp/groups/${chatId}/settings`, { method: "PATCH", body: JSON.stringify({ feature, enabled }) }),
};
