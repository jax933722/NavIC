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
  contact?: { name?: string | null; email?: string | null; role?: string | null } | null;
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

export interface ImportResponse {
  rows: number;
  imported: number;
  skipped: number;
  companies: number;
  signals: number;
  opportunities: number;
  row_errors: string[];
}

export async function importLeads(file: File): Promise<ImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/v1/admin/import`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `API ${res.status}`);
  }
  return res.json();
}

export interface CrawlerStatus {
  running: boolean;
  started_at: string | null;
  cycles: number;
  last_run_at: string | null;
  interval: number;
  sources: string[];
  totals: { companies: number; signals: number; opportunities: number };
  per_source: Record<string, { ok: boolean; error?: string; opportunities?: number }>;
  last_error: string | null;
}

export async function crawlerStatus(): Promise<CrawlerStatus> {
  const res = await fetch(`${API_URL}/v1/admin/crawler/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function crawlerStart(intervalSeconds = 45): Promise<CrawlerStatus> {
  const res = await fetch(
    `${API_URL}/v1/admin/crawler/start?interval_seconds=${intervalSeconds}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function crawlerStop(): Promise<CrawlerStatus> {
  const res = await fetch(`${API_URL}/v1/admin/crawler/stop`, { method: "POST" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export interface SeedTarget {
  id: number;
  source: string;
  url: string;
  company_domain?: string | null;
  company_name?: string | null;
}

export async function listSeeds(): Promise<{ data: SeedTarget[]; sources: string[] }> {
  const res = await fetch(`${API_URL}/v1/admin/seeds`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function addSeed(t: Omit<SeedTarget, "id">): Promise<SeedTarget> {
  const res = await fetch(`${API_URL}/v1/admin/seeds`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(t),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `API ${res.status}`);
  }
  return res.json();
}

export async function deleteSeed(id: number): Promise<void> {
  const res = await fetch(`${API_URL}/v1/admin/seeds/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}`);
}
