import type { EvidenceRef } from "@/lib/api";

// Evidence one click away — trust is the product (spec 07, U1).
export function EvidenceChip({ ev }: { ev: EvidenceRef }) {
  return (
    <a className="chip" href={ev.url} target="_blank" rel="noreferrer" title={ev.snippet ?? ""}>
      <span className="ct">{ev.claim_type}</span>
      {ev.snippet ? ` — ${ev.snippet}` : ""} · {(ev.confidence * 100) | 0}%
    </a>
  );
}
