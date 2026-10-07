export type Provider = "cloud" | "local";
export type Role = "user" | "assistant" | "system";
export interface Message { id: string; session_id: string; role: Role; content: string; created_at: string; }
export interface Session { id: string; created_at: string; active_llm: Provider; messages: Message[]; }
export interface Artifact { type: "html" | "markdown" | string; content: string; }
export interface ModelStatus { cloud: { provider: "gemini" | "openai" | "groq" | "openrouter"; configured: boolean; model: string }; local: { online: boolean; required_model: string; available_models: string[]; error: string | null }; }
