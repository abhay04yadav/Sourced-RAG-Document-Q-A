import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const loadDocs = useCallback(async () => {
    const { data } = await api.get("/documents/");
    setDocs(data);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadDocs();
      } catch (err) {
        if (!cancelled) setError(err.response?.data?.detail || "Failed to load documents");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadDocs]);

  // Poll each processing document every 3s until ready/failed
  useEffect(() => {
    const processingIds = docs.filter((d) => d.status === "processing").map((d) => d.id);
    if (processingIds.length === 0) return undefined;

    const id = setInterval(async () => {
      try {
        const updates = await Promise.all(
          processingIds.map((docId) => api.get(`/documents/${docId}`).then((r) => r.data)),
        );
        setDocs((prev) =>
          prev.map((doc) => {
            const next = updates.find((u) => u.id === doc.id);
            return next
              ? {
                  ...doc,
                  status: next.status,
                  page_count: next.page_count,
                  total_chunks: next.total_chunks,
                  error_message: next.error_message,
                }
              : doc;
          }),
        );
      } catch {
        // keep polling; transient errors are fine
      }
    }, 3000);

    return () => clearInterval(id);
  }, [docs]);

  async function onDelete(docId) {
    if (!window.confirm("Delete this document?")) return;
    try {
      await api.delete(`/documents/${docId}`);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
      setError("");
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to delete document");
    }
  }

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <h1>Documents</h1>
          <p className="muted">{user?.email}</p>
        </div>
        <div className="topbar-actions">
          <Link className="button" to="/upload">
            Upload PDF
          </Link>
          <button type="button" className="button ghost" onClick={() => { logout(); navigate("/login"); }}>
            Log out
          </button>
        </div>
      </header>

      {loading && <p className="muted">Loading documents…</p>}
      {error && <p className="error">{error}</p>}

      {!loading && docs.length === 0 && (
        <p className="muted">No documents yet. Upload a PDF to get started.</p>
      )}

      <ul className="doc-list">
        {docs.map((doc) => (
          <li key={doc.id} className="doc-row">
            <div>
              <strong>{doc.filename}</strong>
              <div className="muted small">
                {doc.page_count} pages · {doc.total_chunks} chunks
              </div>
              {doc.status === "failed" && doc.error_message && (
                <p className="error small">{doc.error_message}</p>
              )}
            </div>
            <div className="doc-actions">
              <StatusBadge status={doc.status} />
              {doc.status === "ready" && (
                <Link className="button small" to={`/chat/${doc.id}`}>
                  Chat
                </Link>
              )}
              <button type="button" className="button ghost small" onClick={() => onDelete(doc.id)}>
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
