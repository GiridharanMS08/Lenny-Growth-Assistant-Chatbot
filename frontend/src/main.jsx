import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = "http://localhost:8000";

function logFrontend(event, detail = "") {
  try {
    fetch(`${API}/logs/frontend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, detail }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Logging must never affect the user flow.
  }
}

function App() {
  const [sid, setSid] = useState(null);
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([]);
  const [sources, setSources] = useState([]);
  const [artifact, setArtifact] = useState(null);
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/sessions`, { method: "POST" })
      .then((r) => {
        if (!r.ok) throw new Error("Could not create session");
        return r.json();
      })
      .then((x) => {
        setSid(x.session_id);
        logFrontend("session.created");
      })
      .catch(() => {
        logFrontend("error.session_create_failed");
        setError("Backend is unavailable. Start the application first.");
      });
  }, []);

  function newChat() {
    location.reload();
  }

  async function send() {
    if (!input.trim() || busy || !sid) return;

    const text = input.trim();
    setInput("");
    setError("");
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    logFrontend("chat.sent", `length=${text.length}`);

    try {
      const r = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          message: text,
        }),
      });

      const x = await r.json();

      if (!r.ok) {
        throw new Error(x.detail || "Chat request failed");
      }

      setSid(x.session_id);
      setProvider(x.provider || "");
      setMsgs((m) => [...m, { role: "assistant", content: x.answer }]);
      setSources(x.sources || []);
      logFrontend("chat.completed", `sources=${(x.sources || []).length}`);

      if (x.artifact?.content) {
        setArtifact(x.artifact);
      } else if (x.intent !== "artifact") {
        setArtifact(null);
      }
    } catch (e) {
      logFrontend("error.chat_failed");
      setError(e.message || "Error connecting to the backend.");
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          content: "I couldn't complete that request. Check the backend/Ollama status.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Lenny Growth Assistant</h1>
          <span>
            Grounded product & growth intelligence
            {provider ? ` · ${provider}` : ""}
          </span>
        </div>
        <button onClick={newChat}>New chat</button>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main>
        <section className="chat">
          {msgs.length === 0 && (
            <div className="welcome">
              <div className="eyebrow">LENNY'S PODCAST</div>
              <h2>Ask about growth, product & startups</h2>
              <p>Try: “What are effective ways to improve activation?”</p>
              <p>Or: “Create a growth strategy document for my SaaS startup.”</p>
            </div>
          )}

          <div className="messages">
            {msgs.map((m, i) => (
              <div className={`msg ${m.role}`} key={i}>
                <b>{m.role === "user" ? "You" : "Assistant"}</b>
                <div>{m.content}</div>
              </div>
            ))}
            {busy && (
              <div className="msg assistant">
                <b>Assistant</b>
                <div className="thinking">Working on it…</div>
              </div>
            )}
          </div>

          <div className="composer">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Ask a product or growth question…"
              disabled={busy}
            />
            <button onClick={send} disabled={busy || !sid}>
              {busy ? "Working…" : "Send"}
            </button>
          </div>
        </section>

        <aside>
          <div className="panel sources-panel">
            <div className="panel-title">
              <h3>Sources</h3>
              <span>{sources.length}</span>
            </div>

            {sources.length ? (
              sources.map((s, i) => (
                <div className="source" key={s.citation_id ?? i}>
                  <b>[{s.citation_id ?? i + 1}] {s.title || "Transcript"}</b>
                  <span>{s.guest || "Lenny's Podcast"}</span>
                  {s.publish_date && <small>{s.publish_date}</small>}
                </div>
              ))
            ) : (
              <p>No retrieved sources yet.</p>
            )}
          </div>

          <div className="panel artifact">
            <div className="panel-title">
              <h3>Artifact Viewer</h3>
              {artifact && <button className="ghost" onClick={() => setArtifact(null)}>Clear</button>}
            </div>

            {artifact?.content ? (
              <iframe
                title="Generated artifact"
                sandbox=""
                srcDoc={artifact.content}
              />
            ) : (
              <div className="artifact-empty">
                <div className="artifact-icon">✦</div>
                <strong>Your generated artifact appears here</strong>
                <p>
                  Ask for a document, roadmap, report, landing page, or HTML artifact.
                </p>
              </div>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
