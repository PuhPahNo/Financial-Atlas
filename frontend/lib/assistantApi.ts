import { ApiError, Envelope } from "@/lib/api";

export interface ArtifactColumn {
  key: string;
  label: string;
  format: string;
}

export interface ArtifactTable {
  id: string;
  title: string;
  columns: ArtifactColumn[];
  rows: Record<string, unknown>[];
}

export interface ArtifactChart {
  id: string;
  title: string;
  type: "line" | "bar";
  x_key: string;
  value_format: string;
  data: Record<string, unknown>[];
  series: { key: string; label: string; color: string }[];
}

export interface ResearchArtifact {
  tables?: ArtifactTable[];
  charts?: ArtifactChart[];
  sources?: { label: string; provider: string; as_of?: string | null }[];
  checks?: { label: string; status: "pass" | "warn" | "info"; detail: string }[];
  budget?: AssistantBudget;
}

export interface AssistantMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  tool_calls?: { tool?: string; status?: string; error?: string }[];
  artifact?: ResearchArtifact;
  optimistic?: boolean;
  error?: boolean;
}

export interface AssistantBudget {
  model: string;
  enabled: boolean;
  limit_usd: number;
  spent_usd: number;
  reserved_usd: number;
  remaining_usd: number;
  qa_limit_usd: number;
  qa_spent_usd: number;
  qa_reserved_usd: number;
  qa_remaining_usd: number;
}

export interface AssistantSessionData {
  session: { id: number; title: string; surface: string; created_at: string };
  messages: AssistantMessage[];
}

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/v1${path}`, { ...init, headers });
  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = json?.error ?? {};
    throw new ApiError(error.code ?? "INTERNAL", error.message ?? `Request failed (${response.status})`, error);
  }
  return json as Envelope<T>;
}

export const assistantApi = {
  createSession: () => request<AssistantSessionData>("/assistant/sessions", {
    method: "POST",
    body: JSON.stringify({ surface: "global", title: "Atlas research" }),
  }),
  getSession: (sessionId: number) => request<AssistantSessionData>(`/assistant/sessions/${sessionId}`),
  sendMessage: (sessionId: number, message: string, pageContext: { path: string; ticker?: string }) =>
    request<AssistantSessionData>(`/assistant/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ message, page_context: pageContext }),
    }),
  budget: () => request<AssistantBudget>("/assistant/budget"),
};
