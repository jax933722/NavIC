"use client";

import { useCallback, useEffect, useState } from "react";
import {
  API_URL,
  crawlerStart,
  crawlerStatus,
  crawlerStop,
  fetchOpportunities,
  type CrawlerStatus,
  type OpportunityCard,
  type StatusFilter,
  type TierFilter,
} from "@/lib/api";
import { OpportunityRow } from "@/components/OpportunityRow";

const TIERS: TierFilter[] = ["all", "gold", "silver", "bronze"];
const STATUSES: StatusFilter[] = ["active", "contacted", "dismissed", "all"];

function CrawlerControl({ onData }: { onData: () => void }) {
  const [status, setStatus] = useState<CrawlerStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await crawlerStatus());
    } catch {
      /* API not up yet */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // While running, poll status + refresh the board so new leads appear live.
  useEffect(() => {
    if (!status?.running) return;
    const id = setInterval(() => {
      refresh();
      onData();
    }, 4000);
    return () => clearInterval(id);
  }, [status?.running, refresh, onData]);

  async function toggle() {
    setBusy(true);
    try {
      setStatus(status?.running ? await crawlerStop() : await crawlerStart());
      onData();
    } finally {
      setBusy(false);
    }
  }

  const running = status?.running ?? false;
  return (
    <div className="card" style={{ marginBottom: 16, display: "flex", alignItems: "center",
      gap: 14, flexWrap: "wrap" }}>
      <button
        className="tierbtn"
        onClick={toggle}
        disabled={busy}
        style={{ fontWeight: 600, minWidth: 130,
          borderColor: running ? "#e06c6c" : "#3fb950",
          color: running ? "#e06c6c" : "#3fb950" }}
      >
        {busy ? "…" : running ? "■ Stop crawling" : "▶ Start crawling"}
      </button>
      <span className="sub" style={{ margin: 0 }}>
        {running ? (
          <>
            <b style={{ color: "#3fb950" }}>● Live</b> — {status?.cycles} cycle
            {status?.cycles === 1 ? "" : "s"} · {status?.totals.opportunities ?? 0} leads found ·
            watching {status?.sources.join(", ") || "—"} · every {status?.interval}s
          </>
        ) : (
          <>Idle. Press start to crawl the free sources now and keep pulling until you stop.</>
        )}
      </span>
      {status?.last_error && (
        <span className="mono" style={{ color: "#c9a34a", fontSize: 12 }}>
          note: {status.last_error}
        </span>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const [tier, setTier] = useState<TierFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("active");
  const [opps, setOpps] = useState<OpportunityCard[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  const load = useCallback(() => {
    fetchOpportunities(tier, status)
      .then((res) => {
        setOpps(res.data);
        setState("ok");
      })
      .catch(() => setState("error"));
  }, [tier, status]);

  useEffect(() => {
    setState("loading");
    load();
  }, [load]);

  return (
    <main className="container">
      <h1 className="h1">Opportunities</h1>
      <p className="sub">Evidence-backed buying signals, ranked. Filter by maturity tier.</p>

      <CrawlerControl onData={load} />

      <div className="tierbar" style={{ display: "flex", alignItems: "center", flexWrap: "wrap" }}>
        {TIERS.map((t) => (
          <button
            key={t}
            className={`tierbtn ${t === tier ? "active" : ""}`}
            onClick={() => setTier(t)}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
        <span style={{ flex: 1 }} />
        <span className="sub" style={{ margin: "0 6px 0 0" }}>
          Export {tier === "all" ? "all" : tier}:
        </span>
        <a className="tierbtn" href={`${API_URL}/v1/export?tier=${tier}&format=csv`}>
          CSV
        </a>
        <a className="tierbtn" href={`${API_URL}/v1/export?tier=${tier}&format=xlsx`}>
          Excel
        </a>
      </div>

      <div className="tierbar" style={{ marginTop: -6 }}>
        <span className="sub" style={{ margin: "0 4px 0 0" }}>Queue:</span>
        {STATUSES.map((s) => (
          <button
            key={s}
            className={`tierbtn ${s === status ? "active" : ""}`}
            onClick={() => setStatus(s)}
          >
            {s[0].toUpperCase() + s.slice(1)}
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
        <div className="empty">
          {status === "active"
            ? "No active leads here. Press Start crawling above, add some via Import / Capture, or check the Contacted / Dismissed queues."
            : `Nothing ${status} yet.`}
        </div>
      )}
      {state === "ok" &&
        opps.map((opp) => (
          <OpportunityRow key={opp.id} opp={opp} onStatusChange={load} />
        ))}
    </main>
  );
}
