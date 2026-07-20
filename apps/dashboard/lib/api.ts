// Typed client for the NavIC API (spec 06). Mirrors apps/api/schemas.py.

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Tier = "gold" | "silver" | "bronze";
export type TierFilter = Tier | "all";

export interface EvidenceRef {
  id: number;
  url: string;
  claim_type: string;
  snippet: string | null;
  confidence: number;
  observed_at: string;
}

export interface CompanyRef {
  id: number;
  name: string | null;
  domain: string | null;
}

export interface OpportunityCard {
  id: number;
  tier: Tier;
  thesis: string | null;
  company: CompanyRef;
  opportunity_score: number;
  department: string | null;
  decision_maker_role: string | null;
  person_name: string | null;
  qualifiers?: {
    service?: string;
    budget?: string;
    timeline?: string;
    engagement?: string[];
    remote?: boolean;
    stack?: string[];
  } | null;
  evidence_refs: EvidenceRef[];
  updated_at: string;
}

export interface OpportunityList {
  data: OpportunityCard[];
  page: { next_cursor: string | null; has_more: boolean; limit: number };
}

export async function fetchOpportunities(tier: TierFilter): Promise<OpportunityList> {
  const res = await fetch(`${API_URL}/v1/opportunities?tier=${tier}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export interface CaptureRequest {
  text: string;
  company_domain: string;
  company_name?: string;
  author_name?: string;
  author_role?: string;
  source_url?: string;
}

export interface CaptureResponse {
  companies: number;
  signals: number;
  detected_signals: string[];
  opportunities: OpportunityCard[];
}

export async function capturedPost(req: CaptureRequest): Promise<CaptureResponse> {
  const res = await fetch(`${API_URL}/v1/admin/capture`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `API ${res.status}`);
  }
  return res.json();
}
