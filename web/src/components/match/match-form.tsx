"use client";

import { Info, Loader2, WandSparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { MatchResultCard } from "@/components/match/match-result-card";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { matchProfile } from "@/lib/api/match";
import type { MatchResult } from "@/lib/types";

const MIN_LENGTH = 10;
const MAX_LENGTH = 5000;
// No server-enforced timeout exists (matching/explain.py's own doc comment:
// sequential LLM calls, ~8s each, 5 by default -> 30-45s typical, ~100s
// worst case if every one times out). 120s gives headroom above the
// documented worst case rather than guessing at a round number.
const CLIENT_TIMEOUT_MS = 120_000;
// Time-boxed, not progress-based: the API returns one atomic JSON response,
// so there is no real intermediate signal to report. This just tells the
// user what's *likely* happening, tuned to the same measured latency.
const STAGE_2_DELAY_MS = 3_000;

type Status = "idle" | "loading" | "error" | "done";

export function MatchForm() {
  const [profileText, setProfileText] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [stage, setStage] = useState<1 | 2>(1);
  const [results, setResults] = useState<MatchResult[]>([]);
  const [llmAvailable, setLlmAvailable] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const abortRef = useRef<AbortController | null>(null);
  const stageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (stageTimerRef.current) clearTimeout(stageTimerRef.current);
    };
  }, []);

  const trimmedLength = profileText.trim().length;
  const tooShort = trimmedLength > 0 && trimmedLength < MIN_LENGTH;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (trimmedLength < MIN_LENGTH || status === "loading") return;

    const controller = new AbortController();
    abortRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), CLIENT_TIMEOUT_MS);

    setStatus("loading");
    setStage(1);
    setErrorMessage("");
    stageTimerRef.current = setTimeout(() => setStage(2), STAGE_2_DELAY_MS);

    try {
      const data = await matchProfile({ profileText, signal: controller.signal });
      setResults(data.items);
      setLlmAvailable(data.llm_available);
      setStatus("done");
    } catch (err) {
      if (controller.signal.aborted) {
        setErrorMessage(
          err instanceof DOMException && err.name === "AbortError"
            ? "Cancelled."
            : "Timed out. The matcher may be under heavy load -- try again.",
        );
      } else if (err instanceof ApiError) {
        setErrorMessage(`Match failed (${err.status}): ${err.message}`);
      } else {
        setErrorMessage("Match failed. Is the API server running?");
      }
      setStatus("error");
    } finally {
      clearTimeout(timeoutId);
      if (stageTimerRef.current) clearTimeout(stageTimerRef.current);
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-md border border-border bg-card p-4">
        <label htmlFor="profile-input" className="font-heading text-sm font-semibold text-foreground">
          Researcher Profile
        </label>
        <textarea
          id="profile-input"
          value={profileText}
          onChange={(e) => setProfileText(e.target.value)}
          maxLength={MAX_LENGTH}
          rows={5}
          disabled={status === "loading"}
          placeholder="e.g. I study machine learning methods for analyzing rural community health outcomes, with a focus on underserved populations."
          className="w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
        />
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            {tooShort
              ? `At least ${MIN_LENGTH} characters (${trimmedLength} so far).`
              : `${trimmedLength}/${MAX_LENGTH} characters.`}
          </p>
          {/* Distinct `key`s force React to unmount/remount rather than patch
              the same <button> node's type attribute in place. Without them,
              clicking Cancel (which resolves the pending fetch synchronously
              enough to flip status before the browser's own click default-action
              finishes) let the browser see a button that had become
              type="submit" by the time it acted -- silently re-submitting the
              form and starting a second request right after the cancel.
              Confirmed via traced logs: handleSubmit fired twice, the second
              time with status "error", from a genuine second dispatched event. */}
          {status === "loading" ? (
            <Button key="cancel" type="button" variant="outline" size="sm" onClick={handleCancel}>
              <X className="size-4" />
              Cancel
            </Button>
          ) : (
            <Button key="submit" type="submit" size="sm" disabled={trimmedLength < MIN_LENGTH}>
              <WandSparkles className="size-4" />
              Find Matches
            </Button>
          )}
        </div>
      </form>

      {status === "loading" && (
        <div className="flex items-center gap-3 rounded-md border border-border bg-card p-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
          {stage === 1
            ? "Ranking opportunities against your profile..."
            : "Generating AI explanations for the top matches -- this can take up to a minute..."}
        </div>
      )}

      {status === "error" && (
        <div className="rounded-md border border-status-closed/30 bg-status-closed/5 p-4 text-sm text-status-closed">
          {errorMessage}
        </div>
      )}

      {status === "done" && (
        <div className="flex flex-col gap-4">
          {!llmAvailable && (
            <div className="flex items-center gap-2 rounded-md border border-status-forecasted/30 bg-status-forecasted/5 p-3 text-sm text-foreground">
              <Info className="size-4 shrink-0 text-status-forecasted" />
              AI-generated explanations are unavailable right now (local LLM unreachable) -- showing
              ranked matches only.
            </div>
          )}
          {results.length === 0 ? (
            <p className="text-sm text-muted-foreground">No matching opportunities found for this profile.</p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">{results.length} matches, ranked by relevance.</p>
              {results.map((r) => (
                <MatchResultCard key={r.foa_id} result={r} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
