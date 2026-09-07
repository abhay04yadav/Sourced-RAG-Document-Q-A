import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "../api/axios";
import ChatMessage from "../components/ChatMessage";

export default function Chat() {
  const { docId } = useParams();
  const [doc, setDoc] = useState(null);
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/documents/${docId}`);
        if (!cancelled) setDoc(data);
      } catch (err) {
        if (!cancelled) setError(err.response?.data?.detail || "Document not found");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [docId]);

  async function onAsk(e) {
    e.preventDefault();
    if (!question.trim() || busy) return;
    setError("");
    setBusy(true);
    const q = question.trim();
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content: q, sources: null }]);
    try {
      const { data } = await api.post("/chat/ask", {
        document_id: docId,
        question: q,
        session_id: sessionId,
      });
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          cached: data.cached,
        },
      ]);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Ask failed");
      setMessages((prev) => prev.slice(0, -1));
      setQuestion(q);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="muted center">Loading chat…</p>;

  if (!doc) {
    return (
      <main className="page">
        <p className="error">{error || "Document not found"}</p>
        <Link to="/">Back to documents</Link>
      </main>
    );
  }

  const canAsk = doc.status === "ready";

  return (
    <main className="page chat-page">
      <header className="topbar">
        <div>
          <h1>{doc.filename}</h1>
          <p className="muted small">
            Status: {doc.status}
            {sessionId && (
              <>
                {" "}
                · session <code>{sessionId.slice(0, 8)}…</code>
              </>
            )}
          </p>
        </div>
        <Link to="/">Documents</Link>
      </header>

      {!canAsk && (
        <p className="error">
          This document is not ready for chat yet (status: {doc.status}).
        </p>
      )}

      <div className="chat-thread">
        {messages.length === 0 && (
          <p className="muted">Ask a question grounded in this PDF.</p>
        )}
        {messages.map((m, i) => (
          <ChatMessage
            key={`${m.role}-${i}`}
            role={m.role}
            content={m.content}
            sources={m.sources}
          />
        ))}
      </div>

      <form className="ask-form" onSubmit={onAsk}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={canAsk ? "Ask about this document…" : "Document not ready"}
          disabled={!canAsk || busy}
        />
        <button type="submit" disabled={!canAsk || busy || !question.trim()}>
          {busy ? "Thinking…" : "Ask"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </main>
  );
}
