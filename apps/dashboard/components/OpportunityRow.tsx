import type { OpportunityCard } from "@/lib/api";
import { TierBadge } from "./TierBadge";
import { EvidenceChip } from "./EvidenceChip";

export function OpportunityRow({ opp }: { opp: OpportunityCard }) {
  const pct = Math.round(opp.opportunity_score * 100);
  return (
    <div className="card">
      <div className="row">
        <div>
          <div className="thesis">{opp.thesis ?? "Opportunity"}</div>
          <div className="company">
            {opp.company.name ?? "Unknown"}{" "}
            {opp.company.domain && <span className="mono">· {opp.company.domain}</span>}
          </div>
          {opp.person_name ? (
            <div className="company">
              ★ {opp.person_name}
              {opp.decision_maker_role ? ` · ${opp.decision_maker_role}` : ""}
            </div>
          ) : (
            opp.decision_maker_role && (
              <div className="company">→ suggested: {opp.decision_maker_role}</div>
            )
          )}
        </div>
        <div style={{ textAlign: "right", minWidth: 120 }}>
          <TierBadge tier={opp.tier} />
          <div className="score">{opp.opportunity_score.toFixed(2)}</div>
          <div className="scorebar">
            <span style={{ width: `${pct}%` }} />
          </div>
        </div>
      </div>
      {opp.evidence_refs.length > 0 && (
        <div className="evidence">
          {opp.evidence_refs.map((ev) => (
            <EvidenceChip key={ev.id} ev={ev} />
          ))}
        </div>
      )}
    </div>
  );
}
