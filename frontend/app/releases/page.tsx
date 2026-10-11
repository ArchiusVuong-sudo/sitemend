"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ComparePanel } from "@/components/compare";
import { useJobs, useSite } from "@/components/jobs";
import { Button, Card, cx, Empty, ErrorNote, Icon, PageHeader, Pill, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { CATEGORY_LABEL, CATEGORY_TONE, KIND_LABEL, STATUS_LABEL, STATUS_TONE, timeAgo } from "@/lib/labels";
import type { Release } from "@/lib/types";

const KIND_TONE: Record<Release["kind"], string> = {
  autopilot: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  deploy: "bg-blue-50 text-blue-700 ring-blue-200",
  revert: "bg-amber-50 text-amber-800 ring-amber-200",
  rollback: "bg-rose-50 text-rose-700 ring-rose-200",
};

export default function ReleasesPage() {
  const site = useSite();
  const { busy, start } = useJobs();
  const releases = useQuery({ queryKey: ["releases"], queryFn: api.releases });
  const [openId, setOpenId] = useState<number | null>(null);
  const list = releases.data ?? [];
  const expanded = openId;

  return (
    <div>
      <PageHeader
        title="Releases"
        subtitle="Each deploy, revert or rollback makes a new numbered release. Releases never change, so any one can be served again exactly."
      />
      {releases.error && <ErrorNote error={releases.error} />}
      {releases.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : list.length === 0 ? (
        <Empty
          title="No releases yet"
          body="Generate fixes: passing fixes in autopilot categories ship as release v1. Approved fixes ship with Deploy."
        />
      ) : (
        <div className="mb-6 space-y-2.5">
          {list.map((r) => {
            const isOpen = expanded === r.id;
            return (
              <Card key={r.id} className={cx(r.active && "ring-2 ring-emerald-500/40")}>
                <div className="flex items-center gap-4 px-5 py-3.5">
                  <button
                    onClick={() => setOpenId(isOpen ? null : r.id)}
                    className="flex min-w-0 flex-1 items-center gap-4 text-left"
                  >
                    <Icon name="chevron" className={cx("size-4 shrink-0 text-slate-400 transition-transform", isOpen && "rotate-90")} />
                    <span className="w-10 text-base font-semibold tabular-nums text-slate-900">{r.label}</span>
                    <Pill tone={KIND_TONE[r.kind]} className="capitalize">
                      {r.kind}
                    </Pill>
                    <span className="truncate text-sm text-slate-600">{r.note}</span>
                  </button>
                  <span className="shrink-0 text-xs tabular-nums text-slate-500">{r.ops.length} fixes</span>
                  <span className="w-20 shrink-0 text-right text-xs text-slate-400">{timeAgo(r.created_at)}</span>
                  <div className="w-36 shrink-0 text-right">
                    {r.active ? (
                      <Pill tone="bg-emerald-600 text-white ring-emerald-600">Active at the edge</Pill>
                    ) : (
                      <Button size="sm" variant="secondary" disabled={busy} onClick={() => start("Rollback", () => api.rollback(r.number))}>
                        <Icon name="undo" className="size-3.5" />
                        Roll back to {r.label}
                      </Button>
                    )}
                  </div>
                </div>
                {isOpen && (
                  <ul className="divide-y divide-slate-100 border-t border-slate-100">
                    {r.ops.length === 0 && <li className="px-5 py-3 text-sm text-slate-500">This release applies no fixes.</li>}
                    {r.ops.map((o) => (
                      <li key={o.fix_id} className="flex items-center gap-4 px-5 py-2.5 pl-14 text-sm">
                        <span className="w-28 shrink-0">
                          <Pill tone={CATEGORY_TONE[o.category]}>{CATEGORY_LABEL[o.category]}</Pill>
                        </span>
                        <span className="w-36 shrink-0 text-[13px] font-medium text-slate-700">
                          {KIND_LABEL[String(o.op.op)] ?? String(o.op.op)}
                        </span>
                        <span className="w-64 shrink-0 truncate font-mono text-xs text-slate-500">{o.path}</span>
                        <span className="min-w-0 flex-1 truncate text-[13px] text-slate-700">{o.fix?.after.split("\n")[0]}</span>
                        {r.active && o.fix && (
                          <>
                            <Pill tone={STATUS_TONE[o.fix.status]}>{STATUS_LABEL[o.fix.status]}</Pill>
                            <Button size="sm" variant="ghost" disabled={busy} onClick={() => start("Revert", () => api.revert(o.fix_id))}>
                              Revert
                            </Button>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            );
          })}
        </div>
      )}
      {site.data?.latest_scan && <ComparePanel activeRelease={site.data.active_release} />}
    </div>
  );
}
