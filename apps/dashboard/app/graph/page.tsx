"use client";

import { useState } from "react";
import { fetchGraph, type Graph } from "@/lib/graph";

const NODE_COLORS: Record<string, string> = {
  company: "#4f8cff",
  person: "#c9a227",
  technology: "#7bd88f",
  post: "#b87333",
  event: "#c678dd",
};

function layout(graph: Graph, cx: number, cy: number, radius: number) {
  const pos = new Map<number, { x: number; y: number }>();
  const root = graph.nodes[0];
  if (root) pos.set(root.id, { x: cx, y: cy });
  const others = graph.nodes.slice(1);
  others.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, others.length);
    pos.set(n.id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) });
  });
  return pos;
}

export default function GraphPage() {
  const [id, setId] = useState("1");
  const [graph, setGraph] = useState<Graph | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");

  async function load() {
    setState("loading");
    try {
      setGraph(await fetchGraph(Number(id)));
      setState("idle");
    } catch {
      setState("error");
    }
  }

  const W = 900;
  const H = 560;
  const pos = graph ? layout(graph, W / 2, H / 2, 200) : null;

  return (
    <main className="container">
      <h1 className="h1">Knowledge Graph Explorer</h1>
      <p className="sub">Neighborhood of a company: people, tech, and relationships.</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        style={{ display: "flex", gap: 8, marginBottom: 16 }}
      >
        <input
          className="tierbtn"
          style={{ width: 120 }}
          value={id}
          onChange={(e) => setId(e.target.value)}
          placeholder="company id"
        />
        <button className="tierbtn active" type="submit">
          Load
        </button>
      </form>

      {state === "loading" && <div className="empty">Loading…</div>}
      {state === "error" && <div className="error">Company not found or API down.</div>}

      {graph && pos && (
        <svg
          width="100%"
          viewBox={`0 0 ${W} ${H}`}
          style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 10 }}
        >
          {graph.edges.map((e, i) => {
            const a = pos.get(e.from);
            const b = pos.get(e.to);
            if (!a || !b) return null;
            return (
              <g key={i}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#3a4453"
                      strokeWidth={1 + e.confidence * 2} />
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 4} fill="#8a94a6"
                      fontSize="10" textAnchor="middle">
                  {e.type}
                </text>
              </g>
            );
          })}
          {graph.nodes.map((n) => {
            const p = pos.get(n.id)!;
            return (
              <g key={n.id}>
                <circle cx={p.x} cy={p.y} r={n.type === "company" ? 22 : 14}
                        fill={NODE_COLORS[n.type] || "#8a94a6"} />
                <text x={p.x} y={p.y + (n.type === "company" ? 38 : 28)} fill="#e6e9ee"
                      fontSize="12" textAnchor="middle">
                  {n.label}
                </text>
                <title>{`${n.type}: ${n.label}`}</title>
              </g>
            );
          })}
        </svg>
      )}
      {graph && graph.nodes.length <= 1 && (
        <div className="empty">No relationships yet for this company.</div>
      )}
    </main>
  );
}
