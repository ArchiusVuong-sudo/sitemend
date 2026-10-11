"use client";

import { useQuery } from "@tanstack/react-query";
import { Fragment, useMemo, useState } from "react";

import { GradeRing, ScoreBar, Stat } from "@/components/grade";
import { useJobs, useSite } from "@/components/jobs";
import {
  Button,
  Card,
  cx,
  Empty,
  ErrorNote,
  Icon,
  PageHeader,
  Pill,
  ProgressBar,
  Skeleton,
  Tooltip,
} from "@/components/ui";
import { api } from "@/lib/api";
import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  CATEGORY_TONE,
  RULE_LABEL,
  SEVERITY_TONE,
  STATUS_LABEL,
  STATUS_TONE,
  timeAgo,
} from "@/lib/labels";
import type { Category, Issue } from "@/lib/types";

export default function OverviewPage() {
  const site = useSite();
  const { active, busy, start } = useJobs();
  const [target, setTarget] = useState<"origin" | "edge">("origin");
  const [filter, setFilter] = useState<Category | "all">("all");
  const [open, setOpen] = useState<number | null>(null);

  const edgeScan = site.data?.latest_edge_scan ?? null;
  const shown = target === "edge" && edgeScan ? "edge" : "origin";
  const issues = useQuery({ queryKey: ["issues", shown], queryFn: () => api.issues(shown) });

  const scanning = active?.kind === "scan";
  const scan = site.data?.latest_scan ?? null;
  const grade = scan?.summary.grade;
  const edgeGrade = edgeScan?.summary.grade;
  const firstGrade = site.data?.first_scan_grade ?? undefined;

  const rows = useMemo(
    () => (issues.data?.issues ?? []).filter((i) => filter === "all" || i.category === filter),
    [issues.data, filter],
  );
  const counts = useMemo(() => {
    const c: Partial<Record<Category, number>> = {};
    for (const i of issues.data?.issues ?? []) c[i.category] = (c[i.category] ?? 0) + 1;
    return c;
  }, [issues.data]);

  const runScan = () => start("Scan", api.scan);

  if (site.error) return <ErrorNote error={site.error} />;

  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle="Crawl the shop, grade it, and rank every issue by what it costs in search."
        actions={
          <Button variant="primary" onClick={runScan} loading={scanning} disabled={busy && !scanning}>
            <Icon name="play" className="size-3.5" />
            {scanning ? "Scanning" : "Run scan"}
          </Button>
        }
      />

      {scanning && active && (
        <Card className="mb-5 px-5 py-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium text-slate-700">Crawling {site.data?.domain}</span>
            <span className="tabular-nums text-slate-500">
              {active.done} of {Math.max(active.total, active.done)} pages crawled
            </span>
          </div>
          <ProgressBar value={active.total ? (active.done / active.total) * 100 : 4} tone="bg-emerald-500" />
        </Card>
      )}

      {site.isLoading ? (
        <Skeleton className="h-56 w-full" />
      ) : !scan ? (
        !scanning && (
          <Empty
            title="No scan yet"
            body="Run a scan to crawl the 12-page synthetic shop, check every page against 9 rules and rank what to fix first."
            action={
              <Button variant="primary" onClick={runScan}>
                <Icon name="play" className="size-3.5" />
                Run scan
              </Button>
            }
          />
        )
      ) : (
        grade && (
          <Card className="mb-6 grid grid-cols-[auto_1fr_auto] items-center gap-10 px-8 py-6">
            <div className="flex items-center gap-6">
              <GradeRing score={grade.site} label="Origin" />
              {edgeGrade && (
                <>
                  <Icon name="chevron" className="size-5 text-slate-300" />
                  <GradeRing score={edgeGrade.site} label="Live edge" />
                </>
              )}
            </div>
            <div className="space-y-4">
              <ScoreBar label="Technical" score={edgeGrade?.technical ?? grade.technical} before={edgeGrade ? grade.technical : undefined} />
              <ScoreBar label="On-page" score={edgeGrade?.onpage ?? grade.onpage} before={edgeGrade ? grade.onpage : undefined} />
              <ScoreBar label="Rich results" score={edgeGrade?.rich ?? grade.rich} before={edgeGrade ? grade.rich : undefined} />
            </div>
            <div className="grid w-64 grid-cols-2 gap-2">
              <Stat label="Pages crawled" value={grade.pages} hint={timeAgo(scan.finished_at)} />
              <Stat label="Clean pages" value={`${edgeGrade?.clean_pages ?? grade.clean_pages}/${grade.pages}`} />
              <Stat label="Open issues" value={edgeScan?.summary.issues_open ?? grade.issues} />
              <Stat
                label="Issues fixed"
                value={edgeScan?.summary.issues_fixed ?? 0}
                hint={edgeScan ? `proven on ${edgeScan.summary.release ?? "edge"}` : "after verify"}
              />
            </div>
            {firstGrade && edgeGrade && firstGrade.site !== grade.site && (
              <p className="col-span-3 -mt-2 text-xs text-slate-400">First scan graded {firstGrade.site}.</p>
            )}
          </Card>
        )
      )}

      {scan && (
        <Card>
          <div className="flex items-center justify-between gap-4 border-b border-slate-100 px-5 py-3.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <FilterChip active={filter === "all"} onClick={() => setFilter("all")}>
                All <span className="text-slate-400">{issues.data?.issues.length ?? 0}</span>
              </FilterChip>
              {CATEGORY_ORDER.map((c) => (
                <FilterChip key={c} active={filter === c} onClick={() => setFilter(c)}>
                  {CATEGORY_LABEL[c]} <span className="text-slate-400">{counts[c] ?? 0}</span>
                </FilterChip>
              ))}
            </div>
            <div className="flex rounded-lg bg-slate-100 p-0.5 text-xs font-medium">
              {(["origin", "edge"] as const).map((t) => (
                <button
                  key={t}
                  disabled={t === "edge" && !edgeScan}
                  onClick={() => setTarget(t)}
                  className={cx(
                    "rounded-md px-3 py-1.5 transition-colors disabled:text-slate-300",
                    shown === t ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800",
                  )}
                >
                  {t === "origin" ? "Origin scan" : "Live edge scan"}
                </button>
              ))}
            </div>
          </div>
          {issues.error ? (
            <div className="p-5">
              <ErrorNote error={issues.error} />
            </div>
          ) : rows.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-slate-500">
              {issues.isLoading ? "Loading issues" : "No open issues here."}
            </p>
          ) : (
            <table className="w-full table-fixed text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs font-medium text-slate-500">
                  <th className="w-32 px-5 py-2.5">Priority</th>
                  <th className="px-3 py-2.5">Issue</th>
                  <th className="w-60 px-3 py-2.5">Page</th>
                  <th className="w-40 px-3 py-2.5">Category</th>
                  <th className="w-24 px-3 py-2.5">Severity</th>
                  <th className="w-40 px-5 py-2.5 text-right">Fix</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((issue, index) => (
                  <IssueRow
                    key={issue.id}
                    issue={issue}
                    rank={index + 1}
                    max={rows[0]?.priority ?? 1}
                    open={open === issue.id}
                    onToggle={() => setOpen(open === issue.id ? null : issue.id)}
                  />
                ))}
              </tbody>
            </table>
          )}
          <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-400">
            Priority = log10(impressions) x (1 + 2 x CTR gap vs the median for the position band) x severity. Search
            numbers are synthetic, 28 days.
          </p>
        </Card>
      )}
    </div>
  );
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors",
        active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
      )}
    >
      {children}
    </button>
  );
}

function IssueRow({
  issue,
  rank,
  max,
  open,
  onToggle,
}: {
  issue: Issue;
  rank: number;
  max: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <Fragment>
      <tr
        className={cx("cursor-pointer border-b border-slate-100 transition-colors hover:bg-slate-50", open && "bg-slate-50")}
        onClick={onToggle}
      >
        <td className="px-5 py-3">
          <Tooltip text={issue.priority_reason}>
            <span className="inline-flex items-center gap-2" tabIndex={0}>
              <span className="w-5 text-xs tabular-nums text-slate-400">#{rank}</span>
              <span className="relative h-1.5 w-10 overflow-hidden rounded-full bg-slate-100">
                <span
                  className="absolute inset-y-0 left-0 rounded-full bg-slate-800"
                  style={{ width: `${Math.max(8, (issue.priority / max) * 100)}%` }}
                />
              </span>
              <span className="text-xs font-medium tabular-nums text-slate-700">{issue.priority.toFixed(1)}</span>
            </span>
          </Tooltip>
        </td>
        <td className="px-3 py-3">
          <div className="flex items-center gap-2">
            <Icon name="chevron" className={cx("size-3.5 shrink-0 text-slate-400 transition-transform", open && "rotate-90")} />
            <div className="min-w-0">
              <div className="truncate font-medium text-slate-900">{RULE_LABEL[issue.rule] ?? issue.rule}</div>
              <div className="truncate text-xs text-slate-500">{issue.message}</div>
            </div>
          </div>
        </td>
        <td className="truncate px-3 py-3 font-mono text-xs text-slate-600" title={issue.path}>{issue.path}</td>
        <td className="px-3 py-3">
          <Pill tone={CATEGORY_TONE[issue.category]}>{CATEGORY_LABEL[issue.category]}</Pill>
        </td>
        <td className="px-3 py-3">
          <Pill tone={SEVERITY_TONE[issue.severity]} className="capitalize">
            {issue.severity}
          </Pill>
        </td>
        <td className="px-5 py-3 text-right">
          {issue.fix ? (
            <Pill tone={STATUS_TONE[issue.fix.status]}>{STATUS_LABEL[issue.fix.status]}</Pill>
          ) : (
            <span className="text-xs text-slate-400">No fix yet</span>
          )}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-slate-100 bg-slate-50">
          <td />
          <td colSpan={5} className="px-3 pb-4 pt-1">
            <div className="mb-1.5 text-xs font-medium text-slate-500">HTML evidence</div>
            <pre className="scrollbar-thin max-h-56 overflow-auto rounded-lg bg-slate-900 px-4 py-3 font-mono text-[12px] leading-relaxed text-slate-100">
              {issue.evidence}
            </pre>
            <p className="mt-2 text-xs text-slate-500">Why it ranks here: {issue.priority_reason}</p>
          </td>
        </tr>
      )}
    </Fragment>
  );
}
