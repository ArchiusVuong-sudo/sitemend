"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Card, cx, Empty, ErrorNote, PageHeader, Pill, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { clock, ms, RUN_LABEL } from "@/lib/labels";
import type { RunDetail, Span } from "@/lib/types";

const KIND_BAR: Record<Span["kind"], string> = {
  task: "bg-slate-800",
  step: "bg-sky-500",
  fetch: "bg-teal-500",
  model: "bg-violet-500",
  tool: "bg-amber-500",
};
const KIND_NAME: Record<Span["kind"], string> = {
  task: "Celery task",
  step: "Step",
  fetch: "Page fetch",
  model: "Model session",
  tool: "Tool call",
};

const STATUS_TONE = {
  done: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  failed: "bg-rose-50 text-rose-700 ring-rose-200",
  running: "bg-blue-50 text-blue-700 ring-blue-200",
  queued: "bg-slate-100 text-slate-600 ring-slate-200",
} as const;

export default function RunsPage() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 3000 });
  const baselines = useQuery({ queryKey: ["baselines"], queryFn: api.baselines });
  const [picked, setPicked] = useState<number | null>(null);
  const runId = picked ?? runs.data?.find((r) => r.kind === "generate")?.id ?? runs.data?.[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["run-detail", runId],
    queryFn: () => api.runDetail(runId as number),
    enabled: runId !== null,
  });

  return (
    <div>
      <PageHeader
        title="Runs"
        subtitle="Every Celery task, page fetch, model session and tool call is stored as a span, with p50 and p95 per step across runs."
      />
      {runs.error && <ErrorNote error={runs.error} />}
      {runs.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : !runs.data?.length ? (
        <Empty title="No runs yet" body="Run a scan to see its trace here." />
      ) : (
        <div className="grid grid-cols-[260px_1fr] gap-5">
          <Card className="h-fit overflow-hidden">
            <ul className="scrollbar-thin max-h-[560px] divide-y divide-slate-100 overflow-y-auto">
              {runs.data.map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => setPicked(r.id)}
                    className={cx(
                      "flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left transition-colors",
                      runId === r.id ? "bg-slate-900 text-white" : "hover:bg-slate-50",
                    )}
                  >
                    <span>
                      <span className="block text-[13px] font-medium">
                        {RUN_LABEL[r.kind]} <span className="opacity-50">#{r.id}</span>
                      </span>
                      <span className={cx("block text-[11px]", runId === r.id ? "text-slate-300" : "text-slate-400")}>
                        {clock(r.created_at)}
                        {r.release ? ` · ${r.release}` : ""}
                      </span>
                    </span>
                    <span className="text-right text-[11px] tabular-nums">
                      {r.status !== "done" ? (
                        <Pill tone={STATUS_TONE[r.status]}>{r.status}</Pill>
                      ) : (
                        <span className={runId === r.id ? "text-slate-300" : "text-slate-500"}>{ms(r.duration_ms)}</span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <div className="min-w-0 space-y-5">
            {detail.data ? <Waterfall run={detail.data} /> : <Skeleton className="h-72 w-full" />}
          </div>
        </div>
      )}

      {baselines.data && baselines.data.length > 0 && (
        <Card className="mt-6">
          <div className="border-b border-slate-100 px-5 py-3.5">
            <h2 className="text-sm font-semibold text-slate-900">Baselines per step, all runs</h2>
            <p className="text-xs text-slate-500">
              Measured from this app&apos;s own spans. Replayed model sessions take milliseconds; their recorded live latency is on each span.
            </p>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs font-medium text-slate-500">
                <th className="px-5 py-2">Step</th>
                <th className="px-3 py-2">Kind</th>
                <th className="px-3 py-2 text-right">Count</th>
                <th className="px-3 py-2 text-right">p50</th>
                <th className="px-3 py-2 text-right">p95</th>
                <th className="px-3 py-2 text-right">Retries</th>
                <th className="px-5 py-2 text-right">Errors</th>
              </tr>
            </thead>
            <tbody>
              {baselines.data.map((b) => (
                <tr key={`${b.name}-${b.kind}`} className="border-b border-slate-50 last:border-0">
                  <td className="px-5 py-2 font-medium text-slate-800">{b.name}</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1.5 text-xs text-slate-600">
                      <span className={cx("size-2 rounded-sm", KIND_BAR[b.kind])} />
                      {KIND_NAME[b.kind]}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{b.count}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{ms(b.p50_ms)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{ms(b.p95_ms)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{b.retries}</td>
                  <td className={cx("px-5 py-2 text-right tabular-nums", b.errors > 0 && "text-rose-700")}>{b.errors}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

/** Spans in tree order (each parent followed by its children, by start time) with their depth. */
function treeOrder(spans: Span[]): { span: Span; depth: number }[] {
  const ids = new Set(spans.map((s) => s.id));
  const children = new Map<number | null, Span[]>();
  for (const s of spans) {
    const parent = s.parent !== null && ids.has(s.parent) ? s.parent : null;
    children.set(parent, [...(children.get(parent) ?? []), s]);
  }
  const byStart = (a: Span, b: Span) => a.started_at.localeCompare(b.started_at) || a.id - b.id;
  const out: { span: Span; depth: number }[] = [];
  const walk = (parent: number | null, depth: number) => {
    for (const s of (children.get(parent) ?? []).sort(byStart)) {
      out.push({ span: s, depth });
      walk(s.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

function Waterfall({ run }: { run: RunDetail }) {
  const [selected, setSelected] = useState<number | null>(null);
  const { rows, spans, t0, total } = useMemo(() => {
    const spans = run.spans;
    const t0 = spans.length ? Math.min(...spans.map((s) => new Date(s.started_at).getTime())) : 0;
    const end = spans.length ? Math.max(...spans.map((s) => new Date(s.started_at).getTime() + s.duration_ms)) : 1;
    return { rows: treeOrder(spans), spans, t0, total: Math.max(1, end - t0) };
  }, [run.spans]);
  const chosen = spans.find((s) => s.id === selected) ?? null;
  const tokens = run.sessions.reduce((n, s) => n + s.input_tokens + s.output_tokens, 0);

  return (
    <>
      <Card>
        <div className="flex flex-col gap-2 border-b border-slate-100 px-5 py-3.5">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              {RUN_LABEL[run.kind]} #{run.id}
            </h2>
            <p className="text-xs text-slate-500">
              {spans.length} spans · {ms(total)} wall time
              {run.sessions.length > 0 &&
                ` · ${run.sessions.length} model sessions (${run.sessions[0].mode}) · ${tokens.toLocaleString()} tokens`}
            </p>
          </div>
          <div className="flex shrink-0 gap-3 whitespace-nowrap text-[11px] text-slate-500">
            {(Object.keys(KIND_BAR) as Span["kind"][]).map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5">
                <span className={cx("size-2 rounded-sm", KIND_BAR[k])} />
                {KIND_NAME[k]}
              </span>
            ))}
          </div>
        </div>
        {spans.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-slate-500">No spans recorded for this run.</p>
        ) : (
          <div className="scrollbar-thin max-h-[420px] overflow-y-auto py-1.5">
            {rows.map(({ span: s, depth }) => {
              const recorded =
                s.kind === "model" && s.attrs.mode === "replay" && typeof s.attrs.latency_ms === "number"
                  ? (s.attrs.latency_ms as number)
                  : null;
              const left = ((new Date(s.started_at).getTime() - t0) / total) * 100;
              const width = Math.max(0.4, (s.duration_ms / total) * 100);
              return (
                <button
                  key={s.id}
                  onClick={() => setSelected(s.id)}
                  className={cx(
                    "grid w-full grid-cols-[260px_1fr_70px] items-center gap-3 px-5 py-1 text-left text-xs hover:bg-slate-50",
                    selected === s.id && "bg-slate-100",
                  )}
                >
                  <span className="truncate" style={{ paddingLeft: depth * 12 }}>
                    <span className={cx("font-medium", s.status === "error" ? "text-rose-700" : "text-slate-800")}>{s.name}</span>
                    {s.label && <span className="ml-1.5 font-mono text-[11px] text-slate-400">{s.label}</span>}
                  </span>
                  <span className="relative h-3.5">
                    <span
                      className={cx("absolute inset-y-0 rounded-sm", s.status === "error" ? "bg-rose-500" : KIND_BAR[s.kind])}
                      style={{ left: `${left}%`, width: `${width}%` }}
                    />
                  </span>
                  <span className="text-right tabular-nums text-slate-500" title={recorded ? `Recorded live session took ${ms(recorded)}` : undefined}>
                    {ms(s.duration_ms)}
                    {recorded !== null && <span className="block text-[10px] text-violet-500">live {ms(recorded)}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </Card>
      {chosen && (
        <Card className="px-5 py-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-900">
              {chosen.name} <span className="font-mono text-xs font-normal text-slate-500">{chosen.label}</span>
            </h3>
            <Pill tone={chosen.status === "error" ? STATUS_TONE.failed : STATUS_TONE.done}>{chosen.status}</Pill>
          </div>
          <dl className="grid grid-cols-4 gap-3 text-xs">
            <div>
              <dt className="text-slate-500">Kind</dt>
              <dd className="font-medium text-slate-800">{KIND_NAME[chosen.kind]}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Duration</dt>
              <dd className="font-medium tabular-nums text-slate-800">{ms(chosen.duration_ms)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Retries</dt>
              <dd className="font-medium tabular-nums text-slate-800">{chosen.retries}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Started</dt>
              <dd className="font-medium tabular-nums text-slate-800">{clock(chosen.started_at)}</dd>
            </div>
          </dl>
          {chosen.error && <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 font-mono text-xs text-rose-800">{chosen.error}</p>}
          {Object.keys(chosen.attrs).length > 0 && (
            <pre className="mt-3 overflow-auto rounded-lg bg-slate-50 px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-700">
              {JSON.stringify(chosen.attrs, null, 2)}
            </pre>
          )}
        </Card>
      )}
    </>
  );
}
