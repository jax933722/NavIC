"use client";

import { useEffect, useRef, useState } from "react";
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

  // The one-click bookmarklet. Built from the live origin so it points back here.
  const bmRef = useRef<HTMLAnchorElement>(null);
  const [bmCode, setBmCode] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const origin = window.location.origin;
    // Grab the selected post text + the page URL, open Capture pre-filled.
    const js =
      "javascript:(function(){" +
      "var t=(window.getSelection&&String(window.getSelection()))||'';" +
      "if(!t){alert('Select the post text on the page first, then click NavIC.');return;}" +
      "window.open('" + origin + "/capture?text='+encodeURIComponent(t)+" +
      "'&source_url='+encodeURIComponent(location.href),'_blank');" +
      "})();";
    setBmCode(js);
    // React strips javascript: hrefs, so set it on the DOM node directly.
    if (bmRef.current) bmRef.current.setAttribute("href", js);
  }, []);

  async function copyBookmarklet() {
    try {
      await navigator.clipboard.writeText(bmCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  // Prefill from the bookmarklet's query string (text=…&source_url=…&…).
  const [prefilled, setPrefilled] = useState(false);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const t = q.get("text");
    if (t) setText(t);
    const su = q.get("source_url");
    if (su) setSourceUrl(su);
    const cd = q.get("company_domain");
    if (cd) setCompanyDomain(cd);
    const cn = q.get("company_name");
    if (cn) setCompanyName(cn);
    const an = q.get("author_name");
    if (an) setAuthorName(an);
    const ar = q.get("author_role");
    if (ar) setAuthorRole(ar);
    if (t || su) setPrefilled(true);
  }, []);

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

      {prefilled && (
        <p
          className="sub"
          style={{
            color: "#3ba55c",
            background: "rgba(59,165,92,0.08)",
            border: "1px solid rgba(59,165,92,0.3)",
            borderRadius: 8,
            padding: "8px 12px",
            marginBottom: 14,
          }}
        >
          ✓ Brought in from the post you were reading. Add the company website below,
          then turn it into an opportunity.
        </p>
      )}

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

      <section
        style={{
          marginTop: 34,
          paddingTop: 22,
          borderTop: "1px solid rgba(255,255,255,0.12)",
        }}
      >
        <h2 className="h1" style={{ fontSize: 20 }}>
          One-click capture (the NavIC bookmarklet)
        </h2>
        <p className="sub">
          Don&rsquo;t want to copy-paste? Drag the button below into your browser&rsquo;s
          bookmarks bar <strong>once</strong>. Then, whenever you&rsquo;re reading a post
          (LinkedIn, Reddit, anywhere), select the text, click{" "}
          <strong>Save to NavIC</strong>, and this page opens already filled in. You stay
          in control of every item — nothing is automated, and it never touches your login.
        </p>

        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          {/* href is set on the node after mount — React blocks javascript: hrefs. */}
          <a
            ref={bmRef}
            href="#"
            onClick={(e) => e.preventDefault()}
            className="tierbtn"
            style={{
              display: "inline-block",
              padding: "10px 18px",
              fontWeight: 600,
              cursor: "grab",
              textDecoration: "none",
            }}
          >
            ⭐ Save to NavIC
          </a>
          <span className="sub" style={{ margin: 0 }}>
            ← drag me to your bookmarks bar
          </span>
        </div>

        <p className="sub" style={{ marginTop: 16, marginBottom: 6 }}>
          Can&rsquo;t drag it? Create a new bookmark by hand and paste this as the URL:
        </p>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start", flexWrap: "wrap" }}>
          <code
            style={{
              flex: "1 1 320px",
              display: "block",
              padding: "10px 12px",
              background: "rgba(0,0,0,0.35)",
              borderRadius: 8,
              fontSize: 12,
              wordBreak: "break-all",
              whiteSpace: "pre-wrap",
            }}
          >
            {bmCode}
          </code>
          <button
            type="button"
            className="tierbtn"
            style={{ padding: "10px 16px", whiteSpace: "nowrap" }}
            onClick={copyBookmarklet}
          >
            {copied ? "Copied ✓" : "Copy"}
          </button>
        </div>
      </section>
    </main>
  );
}
