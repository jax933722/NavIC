import { API_URL, type EvidenceRef } from "./api";

export interface SearchResult {
  type: string;
  id: number;
  name: string | null;
  domain: string | null;
  score: number;
  tier: string | null;
  matched_on: string[];
  evidence_refs: EvidenceRef[];
}

export interface SearchResponse {
  data: SearchResult[];
  interpreted: { structured_filters: string[]; free_text: string; target: string };
  page: { has_more: boolean; limit: number };
}

export async function search(q: string): Promise<SearchResponse> {
  const res = await fetch(`${API_URL}/v1/search?q=${encodeURIComponent(q)}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}
