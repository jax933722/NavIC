import type { Tier } from "@/lib/api";

export function TierBadge({ tier }: { tier: Tier }) {
  return <span className={`badge badge-${tier}`}>{tier}</span>;
}
