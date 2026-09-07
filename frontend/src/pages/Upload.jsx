import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api/axios";

export default function Upload() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    if (!file) {
      setError("Choose a PDF file");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.post("/documents/upload", form);
      navigate("/", { replace: true });
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <header className="topbar">
        <h1>Upload PDF</h1>
        <Link to="/">Back</Link>
      </header>
      <form className="card-form" onSubmit={onSubmit}>
        <label>
          PDF file (max 20 MB)
          <input
            type="file"
            accept=".pdf,application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy || !file}>
          {busy ? "Uploading…" : "Upload"}
        </button>
      </form>
      <p className="muted small">
        After upload the document stays <code>processing</code> until embeddings finish, then you can chat.
      </p>
    </main>
  );
}
