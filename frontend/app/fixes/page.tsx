"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { FixDrawer } from "@/components/fix-drawer";
import { useJobs, useSite } from "@/components/jobs";
import { useToast } from "@/components/toast";
import { Button, Card, cx, Empty, ErrorNote, Icon, PageHeader, Pill, ProgressBar, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import {
  CATEGORY_HINT,
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  KIND_LABEL,
  POLICY_LABEL,
  STATUS_LABEL,
  STATUS_TONE,
} from "@/lib/labels";
import type { Category, Fix } from "@/lib/types";

const POLICY_TONE = {
  autopilot: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  approval: "bg-amber-50 text-amber-800 ring-amber-200",
  off: "bg-slate-100 text-slate-500 ring-slate-200",
} as const;

export default function FixesPage() {
  const site = useSite();
  const { active, busy, start } = useJobs();
  const qc = useQueryClient();
  const toast = useToast();
  const [openId, setOpenId] = useState<number | null>(null);
  const generating = active?.kind === "generate";
  const fixes = useQuery({ queryKey: ["fixes"], queryFn: api.fixes, refetchInterval: generating ? 800 : false });

  const byCategory = useMemo(() => {
    const out: Partial<Record<Category, Fix[]>> = {};
    for (const f of fixes.data ?? []) (out[f.category] ??= []).push(f);
    return out;
  }, [fixes.data]);
  const all = fixes.data ?? [];
  const approved = all.filter((f) => f.status === "approved").length;
  const live = all.filter((f) => f.status === "live" || f.status === "verified").length;
  const verified = all.filter((f) => f.status === "verified").length;
  const waiting = all.filter((f) => f.status === "pending" || f.status === "needs_review").length;

  const bulk = useMutation({
    mutationFn: (c: Category) => api.bulkApprove(c),
    onSuccess: (data, c) => {
      void qc.invalidateQueries({ queryKey: ["fixes"] });
      toast({ tone: "success", title: `${data.approved.length} ${CATEGORY_LABEL[c].toLowerCase()} approved` });
    },
    onError: (err) => toast({ tone: "error", title: "Bulk approve failed", body: (err as Error).message }),
  });

  const hasScan = Boolean(site.data?.latest_scan);
  return (
    <div>
      <PageHeader
        title="Fixes"
        subtitle="Rules fix technical issues. The model writes titles, descriptions and alt text, and every text passes checks first."
        actions={
          <>
            <Button
              onClick={() => start("Generate fixes", api.generate)}
              loading={generating}
              disabled={!hasScan || (busy && !generating)}
            >
              <Icon name="sparkle" className="size-3.5" />
              {generating ? "Writing fixes" : "Generate fixes"}
            </Button>
            <Button
              variant="primary"
              onClick={() => start("Deploy", api.deploy)}
              disabled={approved === 0 || busy}
              loading={active?.kind === "deploy"}
            >
              <Icon name="rocket" className="size-3.5" />
              Deploy{approved ? ` ${approved}` : ""}
            </Button>
            <Button
              variant="success"
              onClick={() => start("Verify", api.verify)}
              disabled={live === 0 || busy}
              loading={active?.kind === "verify"}
            >
              <Icon name="shield" className="size-3.5" />
              Verify
            </Button>
          </>
        }
      />

      {generating && active && (
        <Card className="mb-5 px-5 py-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium text-slate-700">Writing fixes, one model session per page (up to 3 at once)</span>
            <span className="tabular-nums text-slate-500">
              {active.done} of {active.total || "?"} pages done
            </span>
          </div>
          <ProgressBar value={active.total ? (active.done / active.total) * 100 : 5} tone="bg-violet-500" />
        </Card>
      )}

      {all.length > 0 && (
        <div className="mb-6 grid grid-cols-4 gap-3">
          {[
            ["Waiting for review", waiting, "Approve, edit or reject"],
            ["Approved, not deployed", approved, approved ? "Deploy ships them" : "Nothing queued"],
            ["Deployed at the edge", live, site.data?.active_release ? `Release ${site.data.active_release}` : "No release yet"],
            ["Verified live", verified, verified ? "Proven by an edge re-scan" : "Run Verify after a deploy"],
          ].map(([label, value, hint]) => (
            <Card key={label as string} className="px-4 py-3">
              <div className="text-xs font-medium text-slate-500">{label}</div>
              <div className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</div>
              <div className="text-[11px] text-slate-400">{hint}</div>
            </Card>
          ))}
        </div>
      )}

      {fixes.error && <ErrorNote error={fixes.error} />}
      {fixes.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : all.length === 0 ? (
        <Empty
          title={hasScan ? "No fixes yet" : "Scan the site first"}
          body={
            hasScan
              ? "Generate fixes to have rules repair the technical issues and the model write titles, descriptions and alt text."
              : "Fixes are written from the issues a scan finds. Run a scan on the Overview page."
          }
          action={
            hasScan && (
              <Button variant="primary" onClick={() => start("Generate fixes", api.generate)} disabled={busy}>
                <Icon name="sparkle" className="size-3.5" />
                Generate fixes
              </Button>
            )
          }
        />
      ) : (
        <div className="space-y-5">
          {CATEGORY_ORDER.filter((c) => byCategory[c]?.length).map((c) => {
            const rows = byCategory[c] ?? [];
            const mode = site.data?.policies[c] ?? "approval";
            const passing = rows.filter((f) => f.status === "pending" && f.checks_passed && f.confidence === "high").length;
            return (
              <Card key={c}>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 px-5 py-3">
                  <div className="flex items-center gap-3">
                    <h2 className="text-sm font-semibold text-slate-900">{CATEGORY_LABEL[c]}</h2>
                    <Pill tone={POLICY_TONE[mode]}>{POLICY_LABEL[mode]}</Pill>
                    <span className="text-xs text-slate-500">{CATEGORY_HINT[c]}</span>
                  </div>
                  {passing > 0 && (
                    <Button size="sm" onClick={() => bulk.mutate(c)} loading={bulk.isPending && bulk.variables === c}>
                      <Icon name="check" className="size-3.5" />
                      Approve all {passing} passing
                    </Button>
                  )}
                </div>
                <ul className="divide-y divide-slate-100">
                  {rows.map((f) => (
                    <FixRow key={f.id} fix={f} onOpen={() => setOpenId(f.id)} />
                  ))}
                </ul>
              </Card>
            );
          })}
        </div>
      )}
      {openId !== null && <FixDrawer fixId={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function FixRow({ fix, onOpen }: { fix: Fix; onOpen: () => void }) {
  if (fix.status === "writing") {
    return (
      <li className="flex items-center gap-4 px-5 py-3.5">
        <div className="w-56 shrink-0">
          <div className="text-[13px] font-medium text-slate-700">{KIND_LABEL[fix.kind]}</div>
          <div className="truncate font-mono text-xs text-slate-400">{fix.path}</div>
        </div>
        <Skeleton className="h-4 flex-1" />
        <Pill tone={STATUS_TONE.writing}>Writing</Pill>
      </li>
    );
  }
  const failed = fix.checks.filter((c) => !c.passed);
  const tried = fix.attempts_count;
  return (
    <li>
      <button onClick={onOpen} className="flex w-full items-center gap-4 px-5 py-3.5 text-left transition-colors hover:bg-slate-50">
        <div className="w-56 shrink-0">
          <div className="flex items-center gap-1.5 text-[13px] font-medium text-slate-800">
            {KIND_LABEL[fix.kind] ?? fix.kind}
            {fix.source === "model" && (
              <span className="rounded bg-violet-50 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-violet-600">
                Model
              </span>
            )}
          </div>
          <div className="truncate font-mono text-xs text-slate-500">
            {fix.path}
            {fix.kind === "set_alt" && ` · ${fix.target.split("/").pop()}`}
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs text-slate-400 line-through decoration-slate-300">{fix.before || "(none)"}</div>
          <div className="truncate text-[13px] text-slate-900">{fix.after.split("\n")[0] || "(no text)"}</div>
        </div>
        <div className="flex w-44 shrink-0 items-center justify-end gap-2 text-xs">
          {fix.confidence === "low" && <Pill tone="bg-amber-50 text-amber-800 ring-amber-200">Low confidence</Pill>}
          {fix.checks.length > 0 && (
            <span className={cx("inline-flex items-center gap-1 tabular-nums", failed.length ? "text-rose-700" : "text-emerald-700")}>
              <Icon name={failed.length ? "x" : "check"} className="size-3.5" />
              {fix.checks.length - failed.length}/{fix.checks.length} checks
            </span>
          )}
          {fix.source === "model" && tried > 1 && <span className="text-slate-400">{tried} tries</span>}
        </div>
        <div className="w-36 shrink-0 text-right">
          <Pill tone={STATUS_TONE[fix.status]}>{STATUS_LABEL[fix.status]}</Pill>
        </div>
      </button>
    </li>
  );
}
