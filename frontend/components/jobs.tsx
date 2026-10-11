"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError, type Started } from "@/lib/api";
import type { Run } from "@/lib/types";

import { useToast } from "./toast";

interface JobsValue {
  active: Run | null;
  busy: boolean;
  start: (label: string, call: () => Promise<Started>) => Promise<void>;
}

const JobsContext = createContext<JobsValue>({ active: null, busy: false, start: async () => {} });

export function useJobs() {
  return useContext(JobsContext);
}

export function useSite() {
  return useQuery({ queryKey: ["site"], queryFn: api.site, refetchInterval: 10_000 });
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function finishedMessage(run: Run): { title: string; body?: string } {
  const s = run.summary;
  switch (run.kind) {
    case "scan":
      return {
        title: `Scan finished: ${s.grade?.issues ?? 0} issues on ${s.pages ?? 0} pages`,
        body: `Site grade ${s.grade?.site ?? "-"}. ${plural(s.grade?.clean_pages ?? 0, "page is", "pages are")} already clean.`,
      };
    case "generate":
      return s.release
        ? {
            title: `Release ${s.release} went out on autopilot`,
            body: `${s.autopilot} fixes shipped on their own. ${s.waiting} wait for approval.`,
          }
        : { title: `${s.fixes ?? 0} fixes written`, body: `${s.waiting ?? 0} wait for approval.` };
    case "deploy":
      return { title: `Release ${s.release} is live at the edge`, body: `${s.ops} fixes in this release.` };
    case "verify":
      return {
        title: `Edge re-scan: ${s.verified ?? 0} fixes verified live`,
        body: `Grade ${s.grade_before?.site ?? "-"} to ${s.grade?.site ?? "-"}, ${s.issues_fixed ?? 0} issues fixed.`,
      };
    case "revert":
    case "rollback":
      return {
        title: run.kind === "revert" ? `Release ${s.release}: one fix reverted` : `Release ${s.release}: rolled back to ${s.rolled_back_to}`,
        body: `Re-scan of the edge shows ${s.issues_open ?? 0} open issues, grade ${s.grade?.site ?? "-"}.`,
      };
  }
}

export function JobsProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const toast = useToast();
  const site = useSite();
  const [runId, setRunId] = useState<number | null>(null);
  const announced = useRef<Set<number>>(new Set());

  const running = site.data?.running ?? null;
  const watchId = runId ?? running?.id ?? null;

  const run = useQuery({
    queryKey: ["run", watchId],
    // A run deleted by a reset answers 404: treat it as gone instead of polling it forever.
    queryFn: async () => {
      try {
        return await api.run(watchId as number);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
    enabled: watchId !== null,
    // One dropped poll (a dev proxy reset, a 5xx) is retried; a 4xx is a real answer.
    retry: (count, err) => count < 3 && !(err instanceof ApiError && err.status < 500),
    retryDelay: 500,
    refetchInterval: (q) => {
      if (q.state.error || q.state.data === null) return false;
      const status = q.state.data?.status;
      return status === "done" || status === "failed" ? false : 500;
    },
  });

  const current = run.data && run.data.id === watchId ? run.data : null;

  useEffect(() => {
    if (!current || (current.status !== "done" && current.status !== "failed")) {
      if (current && current.kind === "generate") void qc.invalidateQueries({ queryKey: ["fixes"] });
      if (current && current.kind === "scan") void qc.invalidateQueries({ queryKey: ["site"] });
      return;
    }
    if (announced.current.has(current.id)) return;
    announced.current.add(current.id);
    void qc.invalidateQueries();
    if (current.status === "failed") toast({ tone: "error", title: "Job failed", body: current.error });
    else toast({ tone: "success", ...finishedMessage(current) });
    setRunId(null);
  }, [current, qc, toast]);

  const start = useCallback(
    async (label: string, call: () => Promise<Started>) => {
      try {
        const res = await call();
        setRunId(res.run_id);
        void qc.invalidateQueries({ queryKey: ["site"] });
      } catch (err) {
        const message = err instanceof ApiError ? err.message : String(err);
        toast({ tone: "error", title: `${label} did not start`, body: message });
      }
    },
    [qc, toast],
  );

  const active = current && (current.status === "queued" || current.status === "running") ? current : null;
  const starting = runId !== null && run.data === undefined;
  const value = useMemo(() => ({ active, busy: active !== null || starting, start }), [active, starting, start]);
  return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>;
}
