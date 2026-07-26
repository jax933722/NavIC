"use client";

import { useEffect, useState } from "react";
import { decideReview, fetchReviews, type ReviewItem } from "@/lib/admin";

function EntityCard({ e }: { e: ReviewItem["left"] }) {
  return (
    <div className="card" style={{ flex: 1, margin: 0 }}>
      <div className="thesis">{e.name ?? "—"}</div>
      <div className="company mono">{e.domain ?? ""}</div>
      <pre style={{ fontSize: 11, color: "var(--muted)", whiteSpace: "pre-wrap", marginTop: 8 }}>
        {JSON.stringify(e.attributes ?? {}, null, 1)}
      </pre>
    </div>
  );
}

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  const load = () =>
    fetchReviews()
      .then((r) => {
        setItems(r);
        setState("ok");
      })
      .catch(() => setState("error"));

  useEffect(() => {
    load();
  }, []);

  async function decide(id: number, d: "merge" | "no_match") {
    await decideReview(id, d);
    load();
  }

  return (
    <main className="container">
      <h1 className="h1">Entity Resolution — Review Queue</h1>
      <p className="sub">Borderline merge pairs. Under-merge is the safe error — merge only if sure.</p>

      {state === "loading" && <div className="empty">Loading…</div>}
      {state === "error" && <div className="error">Could not reach the API.</div>}
      {state === "ok" && items.length === 0 && <div className="empty">Queue is empty. 🎉</div>}

      {items.map((it) => (
        <div className="card" key={it.id}>
          <div className="company" style={{ marginBottom: 8 }}>
            match probability <span className="score">{it.match_prob.toFixed(2)}</span>
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <EntityCard e={it.left} />
            <EntityCard e={it.right} />
          </div>
          <div className="tierbar" style={{ marginTop: 12 }}>
            <button className="tierbtn active" onClick={() => decide(it.id, "merge")}>
              Merge
            </button>
            <button className="tierbtn" onClick={() => decide(it.id, "no_match")}>
              Not a match
            </button>
          </div>
        </div>
      ))}
    </main>
  );
}
