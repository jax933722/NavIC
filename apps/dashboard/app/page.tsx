"use client";

import { useEffect, useState } from "react";
import { fetchOpportunities, type OpportunityCard, type TierFilter } from "@/lib/api";
import { OpportunityRow } from "@/components/OpportunityRow";

const TIERS: TierFilter[] = ["all", "gold", "silver", "bronze"];

export default function DashboardPage() {
  const [tier, setTier] = useState<TierFilter>("all");
  const [opps, setOpps] = useState<OpportunityCard[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    let active = true;
    setState("loading");
    fetchOpportunities(tier)
      .then((res) => {
        if (!active) return;
        setOpps(res.data);
        setState("ok");
      })
      .catch(() => active && setState("error"));
    return () => {
      active = false;
    };
  }, [tier]);

  return (
    <main className="container">
      <h1 className="h1">Opportunities</h1>
      <p className="sub">Evidence-backed buying signals, ranked. Filter by maturity tier.</p>

      <div className="tierbar">
        {TIERS.map((t) => (
          <button
            key={t}
            className={`tierbtn ${t === tier ? "active" : ""}`}
            onClick={() => setTier(t)}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {state === "loading" && <div className="empty">Loading…</div>}
      {state === "error" && (
        <div className="error">
          Could not reach the API. Is it running on{" "}
          <span className="mono">{process.env.NEXT_PUBLIC_API_URL}</span>?
        </div>
      )}
      {state === "ok" && opps.length === 0 && (
        <div className="empty">No opportunities in this tier yet. Seed some via the API.</div>
      )}
      {state === "ok" && opps.map((opp) => <OpportunityRow key={opp.id} opp={opp} />)}
    </main>
  );
}
