"use client";

import { useState } from "react";
import { capturedPost, type CaptureResponse } from "@/lib/api";
import { OpportunityRow } from "@/components/OpportunityRow";

const EXAMPLE =
  "Can anyone recommend a website designer who is great at creating on-brand " +
  "Shopify product pages that convert? Budget around $2000, need it in 30 days.";

export default function CapturePage() {
  const [text, setText] = useState("");
  const [companyDomain, setCompanyDomain] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [authorName, setAuthorName] = useState("");
  const [authorRole, setAuthorRole] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [res, setRes] = useState<CaptureResponse | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("loading");
    setErr("");
    try {
      const r = await capturedPost({
        text,
        company_domain: companyDomain,
        company_name: companyName || undefined,
        author_name: authorName || undefined,
        author_role: authorRole || undefined,
        source_url: sourceUrl || undefined,
      });
      setRes(r);
      setState("idle");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "failed");
      setState("error");
    }
  }

  const input = { width: "100%", padding: "9px 12px", marginBottom: 10 } as const;

  return (
    <main className="container">
      <h1 className="h1">Capture a post</h1>
      <p className="sub">
        Saw a buying signal while browsing (a request for a vendor, a funding note, a
        &ldquo;we&rsquo;re hiring&rdquo;)? Paste it here and NavIC turns it into an
        evidence-backed opportunity. You choose each item — no scraping, no cost.
      </p>

      <form onSubmit={submit}>
        <textarea
          className="tierbtn"
          style={{ ...input, minHeight: 110 }}
          placeholder={EXAMPLE}
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <input
            className="tierbtn"
            style={{ ...input, flex: "1 1 220px" }}
            placeholder="Company website / domain *  (e.g. acme.com)"
            value={companyDomain}
            onChange={(e) => setCompanyDomain(e.target.value)}
            required
          />
          <input
            className="tierbtn"
            style={{ ...input, flex: "1 1 220px" }}
            placeholder="Company name (optional)"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
          />
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <input
            className="tierbtn"
            style={{ ...input, flex: "1 1 220px" }}
            placeholder="Who posted it (optional) — e.g. Erika Pacini"
            value={authorName}
            onChange={(e) => setAuthorName(e.target.value)}
          />
          <input
            className="tierbtn"
            style={{ ...input, flex: "1 1 220px" }}
            placeholder="Their role (optional) — e.g. Head of Marketing"
            value={authorRole}
            onChange={(e) => setAuthorRole(e.target.value)}
          />
        </div>
        <input
          className="tierbtn"
          style={input}
          placeholder="Link to the post (optional) — kept as evidence"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
        />
        <button className="tierbtn" type="submit" disabled={state === "loading"}>
          {state === "loading" ? "Analyzing…" : "Turn into opportunity"}
        </button>
      </form>

      {state === "error" && (
        <p className="sub" style={{ color: "#e06c6c", marginTop: 12 }}>
          {err}
        </p>
      )}

      {res && (
        <div style={{ marginTop: 20 }}>
          <p className="sub">
            Detected: {res.detected_signals.length ? res.detected_signals.join(", ") : "no signal"}
            {" · "}
            {res.opportunities.length} opportunit
            {res.opportunities.length === 1 ? "y" : "ies"} created/updated.
          </p>
          {res.opportunities.map((o) => (
            <OpportunityRow key={o.id} opp={o} />
          ))}
          {res.detected_signals.length === 0 && (
            <p className="sub">
              No buying signal found in that text. It still recorded the company; try a
              post that states an intent (asking for a vendor, hiring, funding, switching
              tools).
            </p>
          )}
        </div>
      )}
    </main>
  );
}
