import type { ModelStatus, Provider, Session } from "@/lib/types";

const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}/api${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body && "detail" in body ? String(body.detail) : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
export const api = {
  sessions: () => request<Session[]>("/sessions"),
  session: (id: string) => request<Session>(`/sessions/${id}`),
  createSession: (active_llm: Provider) => request<Session>("/sessions", { method: "POST", body: JSON.stringify({ active_llm }) }),
  models: () => request<ModelStatus>("/models"),
  chat: (session_id: string, message: string, active_llm: Provider) => request<{ session_id: string; active_llm: Provider; skill: string; message: Session["messages"][number] }>("/chat", { method: "POST", body: JSON.stringify({ session_id, message, active_llm }) }),
};
