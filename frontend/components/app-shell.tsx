"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Bot, CheckCircle2, ChevronRight, CircleAlert, Code2, Copy, FileText, LoaderCircle, MessageSquarePlus, Send, WifiOff } from "lucide-react";
import { api } from "@/lib/api";
import { parseArtifact } from "@/lib/artifact-parser";
import type { Artifact, Message, ModelStatus, Provider, Session } from "@/lib/types";

const starterPrompts = ["What does Lenny's Podcast say about activation metrics?", "Write a Ship30for30 post about product onboarding.", "Create an HTML landing page for a growth framework."];

function sessionTitle(session: Session): string {
  const first = session.messages.find((message) => message.role === "user")?.content;
  return first ? `${first.slice(0, 34)}${first.length > 34 ? "…" : ""}` : "New conversation";
}
function copy(value: string): void { void navigator.clipboard.writeText(value); }

export function AppShell() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<Session | null>(null);
  const [provider, setProvider] = useState<Provider>("local");
  const [models, setModels] = useState<ModelStatus | null>(null);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { void initialize(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [active?.messages, pending]);
  useEffect(() => {
    if (models?.cloud.provider === "groq" || models?.cloud.provider === "openrouter") setProvider("cloud");
  }, [models, active?.id]);
  async function initialize(): Promise<void> {
    const [sessionsResult, modelsResult] = await Promise.allSettled([api.sessions(), api.models()]);
    if (modelsResult.status === "fulfilled") setModels(modelsResult.value);
    if (sessionsResult.status === "fulfilled") {
      const all = sessionsResult.value;
      setSessions(all);
      if (all[0]) { setActive(all[0]); setProvider(all[0].active_llm); }
    }
    const failure = [sessionsResult, modelsResult].find((result) => result.status === "rejected");
    if (failure?.status === "rejected") {
      setError(failure.reason instanceof Error ? failure.reason.message : "Unable to reach the backend.");
    }
  }
  async function refreshModels(): Promise<void> {
    try {
      setModels(await api.models());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reach the backend.");
    }
  }
  async function createSession(): Promise<void> {
    try { setError(null); const next = await api.createSession(provider); setSessions((current) => [next, ...current]); setActive(next); setArtifact(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create a chat."); }
  }
  async function selectSession(id: string): Promise<void> {
    try { const next = await api.session(id); setActive(next); setProvider(models?.cloud.provider === "groq" || models?.cloud.provider === "openrouter" ? "cloud" : next.active_llm); const last = [...next.messages].reverse().find((item) => item.role === "assistant"); setArtifact(last ? parseArtifact(last.content).artifact : null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load this chat."); }
  }
  async function send(event?: FormEvent): Promise<void> {
    event?.preventDefault(); const message = draft.trim(); if (!message || pending) return;
    let target = active;
    try {
      setError(null); setPending(true); setDraft("");
      if (!target) { target = await api.createSession(provider); setSessions((current) => [target!, ...current]); setActive(target); }
      const optimistic: Message = { id: `local-${Date.now()}`, session_id: target.id, role: "user", content: message, created_at: new Date().toISOString() };
      setActive((current) => current && { ...current, messages: [...current.messages, optimistic] });
      const response = await api.chat(target.id, message, provider);
      const parsed = parseArtifact(response.message.content); if (parsed.artifact) setArtifact(parsed.artifact);
      const updated = await api.session(target.id); setActive(updated); setSessions((current) => [updated, ...current.filter((item) => item.id !== updated.id)]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The message could not be sent."); }
    finally { setPending(false); }
  }
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }
  const cloudName = models?.cloud.provider === "openai" ? "OpenAI" : models?.cloud.provider === "gemini" ? "Gemini" : models?.cloud.provider === "groq" ? "Groq" : models?.cloud.provider === "openrouter" ? "OpenRouter" : "Cloud";
  const statusText = useMemo(() => !models ? "Checking model settings" : provider === "cloud" ? (models.cloud.configured ? `${cloudName} key configured` : `Missing ${cloudName} key`) : (models.local.online ? `Ollama ${models.local.available_models.includes(models.local.required_model) ? "ready" : "model missing"}` : "Ollama offline"), [models, provider, cloudName]);
  const isReady = provider === "cloud" ? Boolean(models?.cloud.configured) : Boolean(models?.local.online && models.local.available_models.includes(models.local.required_model));
  return <main className="h-screen overflow-hidden bg-zinc-950 text-zinc-100">
    <PanelGroup direction="horizontal">
      <Panel defaultSize={20} minSize={15} className="hidden border-r border-zinc-800 md:block"><Sidebar sessions={sessions} activeId={active?.id} onNew={() => void createSession()} onSelect={(id) => void selectSession(id)} /></Panel>
      <PanelResizeHandle className="w-px bg-zinc-800 hover:bg-emerald-600" />
      <Panel defaultSize={artifact ? 43 : 80} minSize={32}><section className="flex h-full min-w-0 flex-col"><Header provider={provider} cloudName={cloudName} setProvider={setProvider} status={statusText} ready={isReady} onRefresh={() => void refreshModels()} />
        {error && <div role="alert" className="mx-5 mt-4 flex items-center gap-2 rounded-lg border border-red-800 bg-red-950/50 p-3 text-sm text-red-200"><CircleAlert size={16}/>{error}</div>}
        <div className="min-h-0 flex-1 overflow-y-auto"><div className="mx-auto max-w-3xl px-5 py-8">
          {!active?.messages.length ? <EmptyState onPrompt={(prompt) => { setDraft(prompt); }} /> : active.messages.filter((message) => message.role !== "system").map((message) => <MessageBubble key={message.id} message={message} />)}
          {pending && <div className="mt-5 flex items-center gap-2 text-sm text-zinc-400"><LoaderCircle className="animate-spin" size={16}/>Thinking with transcript context…</div>}<div ref={bottomRef}/>
        </div></div>
        <form onSubmit={(event) => void send(event)} className="border-t border-zinc-800 bg-zinc-950 p-4"><div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-zinc-700 bg-zinc-900 p-2 focus-within:border-zinc-500"><textarea aria-label="Message" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleKeyDown} disabled={pending} rows={2} placeholder="Ask about growth, activation, retention, or product strategy…" className="min-h-12 flex-1 resize-none bg-transparent px-2 py-1 text-sm outline-none placeholder:text-zinc-500"/><button aria-label="Send message" disabled={!draft.trim() || pending} className="rounded-lg bg-emerald-500 p-2 text-zinc-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"><Send size={18}/></button></div><p className="mx-auto mt-2 max-w-3xl text-xs text-zinc-500">Enter to send · Shift + Enter for a new line · Answers stay grounded in retrieved transcripts.</p></form>
      </section></Panel>
      {artifact && <><PanelResizeHandle className="w-px bg-zinc-800 hover:bg-emerald-600"/><Panel defaultSize={37} minSize={25}><ArtifactPanel artifact={artifact} onClose={() => setArtifact(null)} /></Panel></>}
    </PanelGroup>
  </main>;
}

function Sidebar({ sessions, activeId, onNew, onSelect }: { sessions: Session[]; activeId?: string; onNew: () => void; onSelect: (id: string) => void }) { return <aside className="flex h-full flex-col bg-zinc-950 p-3"><div className="mb-5 flex items-center gap-2 px-2 text-sm font-semibold"><Bot className="text-emerald-400" size={19}/>Lenny Growth Assistant</div><button onClick={onNew} className="mb-4 flex items-center justify-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-900"><MessageSquarePlus size={16}/>New chat</button><div className="min-h-0 flex-1 overflow-y-auto space-y-1">{sessions.length ? sessions.map((session) => <button key={session.id} onClick={() => onSelect(session.id)} className={`w-full rounded-lg px-3 py-2 text-left text-sm ${session.id === activeId ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"}`}>{sessionTitle(session)}</button>) : <p className="p-3 text-sm leading-6 text-zinc-500">No conversations yet. Start by asking about Lenny&apos;s Podcast.</p>}</div><p className="border-t border-zinc-800 px-2 pt-3 text-xs text-zinc-500">Transcript-grounded responses</p></aside>; }
function Header({ provider, cloudName, setProvider, status, ready, onRefresh }: { provider: Provider; cloudName: string; setProvider: (value: Provider) => void; status: string; ready: boolean; onRefresh: () => void }) { return <header className="flex items-center justify-between border-b border-zinc-800 px-5 py-3"><div><h1 className="text-sm font-semibold">Research workspace</h1><p className="text-xs text-zinc-500">Lenny&apos;s Podcast transcript library</p></div><div className="flex items-center gap-2"><span className={`hidden items-center gap-1 text-xs sm:flex ${ready ? "text-emerald-400" : "text-red-400"}`}>{ready ? <CheckCircle2 size={14}/> : <WifiOff size={14}/>} {status}</span><select aria-label="LLM provider" value={provider} onChange={(event) => { setProvider(event.target.value as Provider); onRefresh(); }} className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs outline-none"><option value="local">Local · Ollama</option><option value="cloud">Cloud · {cloudName}</option></select><button aria-label="Refresh model status" title="Refresh model status" onClick={onRefresh} className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800"><ChevronRight size={16}/></button></div></header>; }
function EmptyState({ onPrompt }: { onPrompt: (prompt: string) => void }) { return <div className="py-16"><Bot className="mb-5 text-emerald-400" size={30}/><h2 className="text-2xl font-semibold">What do you want to learn?</h2><p className="mt-2 max-w-lg text-sm leading-6 text-zinc-400">Ask grounded questions, turn insight into a Ship30for30 post, or generate a rendered artifact.</p><div className="mt-8 grid gap-3 sm:grid-cols-3">{starterPrompts.map((prompt) => <button key={prompt} onClick={() => onPrompt(prompt)} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-left text-sm text-zinc-300 hover:border-zinc-600">{prompt}</button>)}</div></div>; }
function MessageBubble({ message }: { message: Message }) { const parsed = message.role === "assistant" ? parseArtifact(message.content) : { visibleContent: message.content }; return <article className={`mb-6 ${message.role === "user" ? "ml-auto max-w-[85%]" : "max-w-3xl"}`}><div className={`mb-2 text-xs font-medium ${message.role === "user" ? "text-right text-zinc-500" : "text-emerald-400"}`}>{message.role === "user" ? "You" : "Lenny Growth Assistant"}</div><div className={`rounded-xl px-4 py-3 text-sm ${message.role === "user" ? "bg-emerald-500 text-zinc-950" : "border border-zinc-800 bg-zinc-900 text-zinc-200"}`}>{message.role === "assistant" ? <div className="markdown"><ReactMarkdown>{parsed.visibleContent || "Generated an artifact in the panel."}</ReactMarkdown></div> : message.content}</div></article>; }
function ArtifactPanel({ artifact, onClose }: { artifact: Artifact; onClose: () => void }) { const [source, setSource] = useState(false); const isHtml = artifact.type === "html"; return <aside className="flex h-full min-w-0 flex-col border-l border-zinc-800 bg-zinc-950"><header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3"><div className="flex items-center gap-2 text-sm font-semibold">{isHtml ? <Code2 size={16}/> : <FileText size={16}/>} {artifact.type} artifact</div><div className="flex gap-1"><button onClick={() => setSource((value) => !value)} className="rounded px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800">{source ? "Preview" : "Source"}</button><button onClick={() => copy(artifact.content)} aria-label="Copy artifact" className="rounded p-1 text-zinc-300 hover:bg-zinc-800"><Copy size={15}/></button><button onClick={onClose} className="rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800">Close</button></div></header><div className="min-h-0 flex-1 p-3">{source || !isHtml ? (isHtml ? <pre className="h-full overflow-auto rounded-lg bg-zinc-900 p-4 text-xs text-zinc-200"><code>{artifact.content}</code></pre> : <div className="markdown h-full overflow-auto rounded-lg border border-zinc-800 bg-zinc-900 p-5 text-sm"><ReactMarkdown>{artifact.content}</ReactMarkdown></div>) : <iframe title="Generated artifact preview" sandbox="" srcDoc={artifact.content} className="h-full w-full rounded-lg border border-zinc-700 bg-white"/>}</div></aside>; }
