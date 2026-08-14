import { apiFetch } from "@/lib/api/client";
import type { MatchResponse } from "@/lib/types";

export interface MatchProfileParams {
  profileText: string;
  k?: number;
  threshold?: number;
  status?: string | null;
  explain?: boolean;
  signal?: AbortSignal;
}

/**
 * Client-side call by design (see lib/api/client.ts) -- the AI Match view is
 * a genuine user interaction with a real wait, not something a Server
 * Component should pre-render. Verified latency (matching/explain.py,
 * MATCHING.md): sequential LLM calls, ~8s each, match_explain_top_k=5
 * default -> 30-45s typical, ~100s worst case if every call times out. No
 * default fetch timeout exists, so callers should race this against their
 * own AbortController-driven timeout rather than assume one.
 */
export function matchProfile({
  profileText,
  k = 10,
  threshold = 0,
  status = "open",
  explain = true,
  signal,
}: MatchProfileParams): Promise<MatchResponse> {
  return apiFetch<MatchResponse>("/api/match", {
    method: "POST",
    body: JSON.stringify({ profile_text: profileText, k, threshold, status, explain }),
    signal,
  });
}
