import { API_URL } from "./api";

export interface CollectorInfo {
  collector: string;
  source: string | null;
  version: string | null;
  capabilities: Record<string, unknown>;
}

export interface ReviewEntity {
  id: number;
  type?: string;
  name?: string | null;
  domain?: string | null;
  attributes?: Record<string, unknown>;
}

export interface ReviewItem {
  id: number;
  match_prob: number;
  features: Record<string, unknown>;
  left: ReviewEntity;
  right: ReviewEntity;
}

export async function fetchCollectors(): Promise<CollectorInfo[]> {
  const res = await fetch(`${API_URL}/v1/admin/collectors`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()).data;
}

export async function fetchReviews(): Promise<ReviewItem[]> {
  const res = await fetch(`${API_URL}/v1/admin/resolution/review`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()).data;
}

export async function decideReview(id: number, decision: "merge" | "no_match"): Promise<void> {
  const res = await fetch(`${API_URL}/v1/admin/resolution/${id}/decide?decision=${decision}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
}
