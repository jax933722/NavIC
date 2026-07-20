import type { OpportunityCard } from "@/lib/api";
import { TierBadge } from "./TierBadge";
import { EvidenceChip } from "./EvidenceChip";

type Q = NonNullable<OpportunityCard["qualifiers"]>;

function Qualifiers({ q }: { q: Q }) {
  const parts: string[] = [];
  if (q.budget) parts.push(`💰 ${q.budget}`);
  if (q.timeline) parts.push(`⏱ ${q.timeline}`);
  if (q.engagement?.length) parts.push(q.engagement.join(" / "));
  if (q.remote) parts.push("Remote");
  if (q.stack?.length) parts.push(q.stack.slice(0, 6).join(", "));
  if (parts.length === 0) return null;
  return (
    <div className="company" style={{ marginTop: 4, opacity: 0.9 }}>
      🎯 wants <b>{(q.service ?? "").replace(/_/g, " ")}</b>
      {parts.length ? ` — ${parts.join(" · ")}` : ""}
    </div>
  );
}

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
          {opp.qualifiers && <Qualifiers q={opp.qualifiers} />}
          {opp.contact && (opp.contact.name || opp.contact.email) && (
            <div className="company" style={{ marginTop: 4 }}>
              ✉️ {opp.contact.name ?? "Contact"}
              {opp.contact.email ? (
                <>
                  {" · "}
                  <a href={`mailto:${opp.contact.email}`}>{opp.contact.email}</a>
                </>
              ) : (
                " · email not provided"
              )}
            </div>
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
