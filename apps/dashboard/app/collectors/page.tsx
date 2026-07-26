"use client";

import { useEffect, useState } from "react";
import { fetchCollectors, type CollectorInfo } from "@/lib/admin";

export default function CollectorsPage() {
  const [collectors, setCollectors] = useState<CollectorInfo[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    fetchCollectors()
      .then((c) => {
        setCollectors(c);
        setState("ok");
      })
      .catch(() => setState("error"));
  }, []);

  return (
    <main className="container">
      <h1 className="h1">Collectors</h1>
      <p className="sub">Registered pluggable sources. New sources need only a module + @register.</p>

      {state === "loading" && <div className="empty">Loading…</div>}
      {state === "error" && <div className="error">Could not reach the API.</div>}

      {collectors.map((c) => (
        <div className="card" key={c.collector}>
          <div className="row">
            <div>
              <div className="thesis">{c.collector}</div>
              <div className="company">
                source: <span className="mono">{c.source}</span> · v{c.version}
              </div>
            </div>
            <div className="company" style={{ textAlign: "right" }}>
              {Object.entries(c.capabilities)
                .filter(([, v]) => v === true || typeof v === "string")
                .map(([k, v]) => `${k}=${v}`)
                .join(" · ")}
            </div>
          </div>
        </div>
      ))}
    </main>
  );
}
