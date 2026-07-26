import { API_URL } from "./api";

export interface GraphNode {
  id: number;
  type: string;
  label: string | null;
}
export interface GraphEdge {
  type: string;
  from: number;
  to: number;
  confidence: number;
  evidence_ids: number[];
}
export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export async function fetchGraph(companyId: number, depth = 2): Promise<Graph> {
  const res = await fetch(`${API_URL}/v1/companies/${companyId}/graph?depth=${depth}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}
