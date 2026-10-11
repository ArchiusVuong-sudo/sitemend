"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

import { Card, cx, ErrorNote, Skeleton } from "./ui";

function useEdgeHeader(path: string, version: string | undefined) {
  const [header, setHeader] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`/edge${path === "/" ? "/" : path}`, { cache: "no-store" })
      .then((res) => !cancelled && setHeader(res.headers.get("x-sitemend-release")))
      .catch(() => !cancelled && setHeader(null));
    return () => {
      cancelled = true;
    };
  }, [path, version]);
  return header;
}

export function ComparePanel({ activeRelease }: { activeRelease: string | null }) {
  const pages = useQuery({ queryKey: ["pages"], queryFn: api.pages });
  const [path, setPath] = useState("/products/speckled-stoneware-mug");
  const [changedOnly, setChangedOnly] = useState(true);
  const diff = useQuery({ queryKey: ["compare", path, activeRelease], queryFn: () => api.compare(path) });
  const header = useEdgeHeader(path, activeRelease ?? undefined);

  const rows = diff.data?.rows ?? [];
  const visible = changedOnly
    ? rows.filter((r, i) => r.type !== "same" || rows.slice(Math.max(0, i - 2), i + 3).some((x) => x.type !== "same"))
    : rows;

  return (
    <Card>
      <div className="flex items-center justify-between gap-4 border-b border-slate-100 px-5 py-3.5">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Compare origin and edge</h2>
          <p className="text-xs text-slate-500">The origin HTML is never edited. The edge applies the active release when it serves the page.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="h-8 rounded-lg border border-slate-300 bg-white px-2 font-mono text-xs"
            aria-label="Page"
          >
            {(pages.data ?? [{ path, title: "" }]).map((p) => (
              <option key={p.path} value={p.path}>
                {p.path}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-slate-600">
            <input type="checkbox" checked={changedOnly} onChange={(e) => setChangedOnly(e.target.checked)} />
            Changed lines only
          </label>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-slate-100 bg-slate-50 px-5 py-2 font-mono text-[11px] text-slate-600">
        <span>GET /origin{path}</span>
        <span>
          GET /edge{path} <span className="text-slate-400">-&gt;</span> X-Sitemend-Release:{" "}
          <span className="font-semibold text-slate-900">{header ?? "..."}</span>
        </span>
        {diff.data && (
          <span>
            <span className="text-emerald-700">+{diff.data.added}</span> <span className="text-rose-700">-{diff.data.removed}</span> lines
          </span>
        )}
      </div>
      {diff.error ? (
        <div className="p-5">
          <ErrorNote error={diff.error} />
        </div>
      ) : !diff.data ? (
        <div className="space-y-2 p-5">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      ) : diff.data.identical ? (
        <p className="px-5 py-8 text-center text-sm text-slate-500">
          The edge serves this page byte for byte as the origin sends it{activeRelease ? ` (no fixes for it in ${activeRelease})` : ""}.
        </p>
      ) : (
        <div className="scrollbar-thin max-h-[460px] overflow-auto">
          <table className="w-full border-collapse font-mono text-[12px] leading-relaxed">
            <tbody>
              {visible.map((r, i) => {
                const gap = i > 0 && changedOnly && rows.indexOf(r) - rows.indexOf(visible[i - 1]) > 1;
                return (
                  <tr
                    key={`${r.type}-${r.old}-${r.new}`}
                    className={cx(
                      r.type === "added" && "bg-emerald-50",
                      r.type === "removed" && "bg-rose-50",
                      gap && "border-t border-dashed border-slate-200",
                    )}
                  >
                    <td className="w-10 select-none px-2 text-right text-slate-400">{r.old ?? ""}</td>
                    <td className="w-10 select-none px-2 text-right text-slate-400">{r.new ?? ""}</td>
                    <td
                      className={cx(
                        "w-5 select-none text-center",
                        r.type === "added" ? "text-emerald-700" : r.type === "removed" ? "text-rose-700" : "text-slate-300",
                      )}
                    >
                      {r.type === "added" ? "+" : r.type === "removed" ? "-" : ""}
                    </td>
                    <td
                      className={cx(
                        "whitespace-pre-wrap break-all py-0.5 pr-4",
                        r.type === "added" ? "text-emerald-900" : r.type === "removed" ? "text-rose-900" : "text-slate-600",
                      )}
                    >
                      {r.text}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
