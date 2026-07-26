"use client";

import { useState } from "react";
import { importLeads, type ImportResponse } from "@/lib/api";

const SAMPLE =
  "name,company domain,requirement,email\n" +
  "Priya Nair,brightbrew.co,Looking for a Shopify web designer. Budget $2000, 30 days.,priya@brightbrew.co\n" +
  "Marcus Reed,securewpstudio.com,Need a WordPress malware removal expert. Remote.,\n";

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<ImportResponse | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setState("loading");
    setErr("");
    setRes(null);
    try {
      setRes(await importLeads(file));
      setState("idle");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "failed");
      setState("error");
    }
  }

  function downloadSample() {
    const blob = new Blob([SAMPLE], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "navic-leads-template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="container">
      <h1 className="h1">Import leads</h1>
      <p className="sub">
        Upload an Excel (<span className="mono">.xlsx</span>) or{" "}
        <span className="mono">.csv</span> file of leads. Each row becomes an
        evidence-backed opportunity, with the requirement classified automatically and
        the contact kept for outreach.
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <b>Columns</b> (header row required; order and extra columns don&rsquo;t matter):
        <ul style={{ margin: "8px 0 0 18px", lineHeight: 1.7 }}>
          <li>
            <b>company domain</b> — required (e.g. <span className="mono">acme.com</span>).
            Rows without it are skipped.
          </li>
          <li>
            <b>requirement</b> — what they&rsquo;re looking for (the post / need). Classified
            into service, budget, timeline, stack.
          </li>
          <li>
            <b>name</b> — the contact&rsquo;s name (optional).
          </li>
          <li>
            <b>email</b> — the contact&rsquo;s email if you have it (optional — leave blank and
            you can find it later).
          </li>
        </ul>
        <button className="tierbtn" style={{ marginTop: 10 }} onClick={downloadSample}>
          Download a sample template (.csv)
        </button>
      </div>

      <form onSubmit={submit}>
        <input
          type="file"
          accept=".xlsx,.csv"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          style={{ marginBottom: 10, display: "block" }}
        />
        <button className="tierbtn" type="submit" disabled={!file || state === "loading"}>
          {state === "loading" ? "Importing…" : "Import"}
        </button>
      </form>

      {state === "error" && (
        <p className="sub" style={{ color: "#e06c6c", marginTop: 12 }}>
          {err}
        </p>
      )}

      {res && (
        <div className="card" style={{ marginTop: 16 }}>
          <b>
            Imported {res.imported} of {res.rows} rows
          </b>{" "}
          — {res.opportunities} opportunities, {res.signals} signals
          {res.skipped > 0 ? `, ${res.skipped} skipped` : ""}.
          {res.row_errors.length > 0 && (
            <ul style={{ margin: "8px 0 0 18px", color: "#c9a34a" }}>
              {res.row_errors.map((e, i) => (
                <li key={i} className="mono">
                  {e}
                </li>
              ))}
            </ul>
          )}
          <p className="sub" style={{ marginTop: 10 }}>
            Head to <a href="/">Opportunities</a> to see them on the board.
          </p>
        </div>
      )}
    </main>
  );
}
