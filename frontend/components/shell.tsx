"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { RUN_LABEL } from "@/lib/labels";

import { useJobs, useSite } from "./jobs";
import { cx, Icon, Spinner } from "./ui";

const NAV = [
  { href: "/", label: "Overview", icon: "overview" },
  { href: "/fixes", label: "Fixes", icon: "fixes" },
  { href: "/releases", label: "Releases", icon: "releases" },
  { href: "/runs", label: "Runs", icon: "runs" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

function ModeBadge() {
  const { data } = useSite();
  if (!data) return null;
  const live = data.llm.mode === "live";
  return (
    <span
      title={data.llm.reason}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset",
        live ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-amber-50 text-amber-800 ring-amber-200",
      )}
    >
      <span className={cx("size-1.5 rounded-full", live ? "bg-emerald-500" : "bg-amber-500")} />
      {live ? `Live model: ${data.llm.model}` : "Replay mode"}
    </span>
  );
}

function JobChip() {
  const { active } = useJobs();
  if (!active) return null;
  const pct = active.total ? Math.round((active.done / active.total) * 100) : null;
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
      <Spinner className="size-3" />
      {RUN_LABEL[active.kind]}
      {active.total > 0 && (
        <span className="tabular-nums text-slate-300">
          {active.done}/{active.total}
          {pct !== null ? ` (${pct}%)` : ""}
        </span>
      )}
    </span>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data } = useSite();
  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white px-3 py-5">
        <Link href="/" className="mb-7 flex items-center gap-2.5 px-2">
          <span className="grid size-8 place-items-center rounded-lg bg-emerald-600 text-white">
            <Icon name="fixes" className="size-4" />
          </span>
          <span>
            <span className="block text-[15px] font-semibold leading-tight">Sitemend</span>
            <span className="block text-[11px] text-slate-500">SEO fixes, checked and proven</span>
          </span>
        </Link>
        <nav className="flex flex-col gap-0.5">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cx(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                  active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                )}
              >
                <Icon name={item.icon} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto rounded-lg bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-500">
          Demo on a made-up shop. Pages, search numbers and results all come from synthetic data and this
          app&apos;s own runs.
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-slate-200 bg-white/90 px-8 backdrop-blur">
          <div className="flex min-w-0 items-center gap-3">
            <span className="truncate text-sm font-semibold">{data?.name ?? "Loading site"}</span>
            <span className="truncate font-mono text-xs text-slate-500">{data?.domain}</span>
            <span className="inline-flex items-center rounded-full bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700 ring-1 ring-inset ring-violet-200">
              Synthetic site and search data
            </span>
          </div>
          <div className="flex items-center gap-2">
            <JobChip />
            {data?.active_release && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-200">
                <span className="size-1.5 rounded-full bg-emerald-500" />
                Edge release {data.active_release}
              </span>
            )}
            <ModeBadge />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1180px] flex-1 px-8 py-7">{children}</main>
      </div>
    </div>
  );
}
