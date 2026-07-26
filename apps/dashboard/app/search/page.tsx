"use client";

import { useState } from "react";
import { search, type SearchResponse } from "@/lib/search";
import { TierBadge } from "@/components/TierBadge";
import { EvidenceChip } from "@/components/EvidenceChip";

const EXAMPLES = [
  "companies hiring SDR",
  "companies using HubSpot",
  "companies looking for CRM",
  "people discussing deliverability",
];

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<SearchResponse | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");

  async function run(query: string) {
    setQ(query);
    if (!query.trim()) return;
    setState("loading");
    try {
      setRes(await search(query));
      setState("idle");
    } catch {
      setState("error");
    }
  }

  return (
    <main className="container">
      <h1 className="h1">Search</h1>
      <p className="sub">Structured + full-text. Try the examples or type your own.</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(q);
        }}
      >
        <input
          className="tierbtn"
          style={{ width: "100%", padding: "10px 14px", marginBottom: 10 }}
          placeholder="companies hiring SDR using HubSpot…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </form>

      <div className="tierbar" style={{ flexWrap: "wrap" }}>
        {EXAMPLES.map((ex) => (
          <button key={ex} className="tierbtn" onClick={() => run(ex)}>
            {ex}
          </button>
        ))}
      </div>

      {res && (
        <p className="sub">
          Interpreted as:{" "}
          {res.interpreted.structured_filters.length > 0 ? (
            <span className="mono">{res.interpreted.structured_filters.join(", ")}</span>
          ) : (
            <em>free text “{res.interpreted.free_text}”</em>
          )}
        </p>
      )}

      {state === "loading" && <div className="empty">Searching…</div>}
      {state === "error" && <div className="error">Could not reach the API.</div>}
      {res && res.data.length === 0 && <div className="empty">No matches.</div>}

      {res?.data.map((r) => (
        <div className="card" key={`${r.type}-${r.id}`}>
          <div className="row">
            <div>
              <div className="thesis">
                {r.name} {r.domain && <span className="mono company">· {r.domain}</span>}
              </div>
              <div className="company">
                {r.type} · matched {r.matched_on.join(", ")}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              {r.tier && <TierBadge tier={r.tier as "gold" | "silver" | "bronze"} />}
              <div className="score">{r.score.toFixed(2)}</div>
            </div>
          </div>
          {r.evidence_refs.length > 0 && (
            <div className="evidence">
              {r.evidence_refs.map((ev) => (
                <EvidenceChip key={ev.id} ev={ev} />
              ))}
            </div>
          )}
        </div>
      ))}
    </main>
  );
}
