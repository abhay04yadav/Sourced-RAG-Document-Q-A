import { useState } from "react";

/** "Page 3", or "Pages 3–4" when the chunk spans a page break. */
function pageLabel({ page_number, page_end }) {
  return page_end && page_end !== page_number
    ? `Pages ${page_number}–${page_end}`
    : `Page ${page_number}`;
}

/**
 * Chat bubble with optional expandable citations (page + chunk text).
 */
export default function ChatMessage({ role, content, sources }) {
  const [open, setOpen] = useState(false);
  const isUser = role === "user";
  const citationList = sources || [];

  return (
    <div className={`bubble-row ${isUser ? "user" : "assistant"}`}>
      <div className={`bubble ${isUser ? "bubble-user" : "bubble-assistant"}`}>
        <p className="bubble-role">{isUser ? "You" : "Assistant"}</p>
        <p className="bubble-text">{content}</p>
        {!isUser && citationList.length > 0 && (
          <div className="citations">
            <button
              type="button"
              className="linkish"
              onClick={() => setOpen((v) => !v)}
            >
              {open ? "Hide citations" : `Show citations (${citationList.length})`}
            </button>
            {open && (
              <ul className="citation-list">
                {citationList.map((s, i) => (
                  <li key={`${s.chunk_index}-${i}`}>
                    <strong>{pageLabel(s)}</strong>
                    {typeof s.chunk_index === "number" && (
                      <span className="muted"> · chunk {s.chunk_index}</span>
                    )}
                    <p className="citation-text">{s.chunk_text}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
