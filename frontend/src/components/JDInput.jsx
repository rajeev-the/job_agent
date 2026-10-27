import { useState } from "react";
import axios from "axios";
import { API } from "../config";

export default function JDInput({ onNext }) {
  const [mode, setMode] = useState("link"); // "link" | "text" | "pdf"
  const [linkUrl, setLinkUrl] = useState("");
  const [jdText, setJdText] = useState("");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState("");
  const [error, setError] = useState("");

  const handleAnalyse = async () => {
    setError("");
    setLoading(true);

    try {
      let result;
      let textContent = "";

      if (mode === "link") {
        if (!linkUrl.trim()) {
          setError("Please paste a LinkedIn, Instagram, or career page link first!");
          setLoading(false);
          return;
        }
        setLoadingMsg("Scraping link and extracting job details...");
        const res = await axios.post(`${API}/parse-link`, { url: linkUrl.trim() });
        result = res.data;
        textContent = result.jd_text || "";
      } else if (mode === "pdf") {
        if (!file) {
          setError("Please select a PDF file first!");
          setLoading(false);
          return;
        }
        setLoadingMsg("Reading PDF and extracting details...");
        const formData = new FormData();
        formData.append("file", file);
        const res = await axios.post(`${API}/parse-jd-pdf`, formData);
        result = res.data;
        textContent = result.jd_text || "";
      } else {
        if (!jdText.trim()) {
          setError("Please paste a job description first!");
          setLoading(false);
          return;
        }
        setLoadingMsg("Analyzing job description text...");
        const res = await axios.post(`${API}/parse-jd`, { jd_text: jdText });
        result = res.data;
        textContent = jdText;
      }

      if (!result.success) {
        setError(result.error || "Something went wrong while analyzing the job posting.");
        setLoading(false);
        return;
      }

      onNext(result, textContent);
    } catch (err) {
      setError(
        err.response?.data?.error ||
        "Backend not reachable. Make sure FastAPI server is running on port 8000!"
      );
    }

    setLoading(false);
  };

  const isButtonDisabled =
    loading ||
    (mode === "link" && !linkUrl.trim()) ||
    (mode === "text" && !jdText.trim()) ||
    (mode === "pdf" && !file);

  return (
    <div className="card">
      <div className="card-title">Job Description Input</div>
      <div className="card-sub">
        Provide a link, paste raw text, or upload a PDF — AI will automatically extract the HR email, company, role, and requirements.
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          marginBottom: "24px",
          background: "var(--surface2)",
          padding: "4px",
          borderRadius: "10px",
          border: "1px solid var(--border)"
        }}
      >
        <button
          type="button"
          onClick={() => { setMode("link"); setError(""); }}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: "8px",
            border: "none",
            background: mode === "link" ? "var(--accent)" : "transparent",
            color: mode === "link" ? "white" : "var(--muted)",
            fontWeight: mode === "link" ? "700" : "500",
            cursor: "pointer",
            fontFamily: "Syne, sans-serif",
            fontSize: "13px",
            transition: "all 0.2s"
          }}
        >
          🔗 Paste Link
        </button>
        <button
          type="button"
          onClick={() => { setMode("text"); setError(""); }}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: "8px",
            border: "none",
            background: mode === "text" ? "var(--accent)" : "transparent",
            color: mode === "text" ? "white" : "var(--muted)",
            fontWeight: mode === "text" ? "700" : "500",
            cursor: "pointer",
            fontFamily: "Syne, sans-serif",
            fontSize: "13px",
            transition: "all 0.2s"
          }}
        >
          📝 Paste Text
        </button>
        <button
          type="button"
          onClick={() => { setMode("pdf"); setError(""); }}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: "8px",
            border: "none",
            background: mode === "pdf" ? "var(--accent)" : "transparent",
            color: mode === "pdf" ? "white" : "var(--muted)",
            fontWeight: mode === "pdf" ? "700" : "500",
            cursor: "pointer",
            fontFamily: "Syne, sans-serif",
            fontSize: "13px",
            transition: "all 0.2s"
          }}
        >
          📄 Upload PDF
        </button>
      </div>

      {/* Mode: Link */}
      {mode === "link" && (
        <div>
          <input
            type="url"
            placeholder="e.g. https://www.linkedin.com/jobs/view/... or https://instagram.com/p/..."
            value={linkUrl}
            onChange={e => setLinkUrl(e.target.value)}
            style={{ marginBottom: "12px" }}
          />
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "8px",
              marginTop: "4px",
              fontSize: "12px",
              color: "var(--muted)"
            }}
          >
            <span style={{ background: "rgba(108, 99, 255, 0.12)", color: "var(--accent)", padding: "3px 8px", borderRadius: "4px" }}>
              ✓ LinkedIn Jobs & Posts
            </span>
            <span style={{ background: "rgba(255, 101, 132, 0.12)", color: "var(--accent2)", padding: "3px 8px", borderRadius: "4px" }}>
              ✓ Instagram Hiring Posts
            </span>
            <span style={{ background: "rgba(78, 204, 163, 0.12)", color: "var(--success)", padding: "3px 8px", borderRadius: "4px" }}>
              ✓ Indeed / Greenhouse / Lever / Company Portals
            </span>
          </div>
        </div>
      )}

      {/* Mode: Text */}
      {mode === "text" && (
        <textarea
          rows={10}
          placeholder="Paste the full job description here including HR email..."
          value={jdText}
          onChange={e => setJdText(e.target.value)}
        />
      )}

      {/* Mode: PDF */}
      {mode === "pdf" && (
        <div
          onClick={() => document.getElementById("pdf-upload").click()}
          style={{
            border: `2px dashed ${file ? "var(--success)" : "var(--border)"}`,
            borderRadius: "10px",
            padding: "36px 24px",
            textAlign: "center",
            cursor: "pointer",
            color: file ? "var(--success)" : "var(--muted)",
            fontSize: "14px",
            transition: "all 0.2s",
            background: file ? "rgba(78, 204, 163, 0.05)" : "transparent"
          }}
        >
          {file ? `✅ Selected: ${file.name}` : "📄 Click to choose or drop JD PDF file"}
          <input
            id="pdf-upload"
            type="file"
            accept=".pdf"
            style={{ display: "none" }}
            onChange={e => setFile(e.target.files[0])}
          />
        </div>
      )}

      {error && (
        <div style={{ color: "var(--accent2)", fontSize: "13px", marginTop: "16px" }}>
          ⚠️ {error}
        </div>
      )}

      <div className="btn-row" style={{ marginTop: "24px" }}>
        <button
          className="btn-primary"
          onClick={handleAnalyse}
          disabled={isButtonDisabled}
        >
          {loading ? (loadingMsg || "Analyzing...") : "Analyse & Continue →"}
        </button>
      </div>
    </div>
  );
}
