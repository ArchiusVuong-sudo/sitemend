"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { CATEGORY_LABEL, KIND_LABEL, ms, STATUS_LABEL, STATUS_TONE } from "@/lib/labels";
import type { Check, FixDetail } from "@/lib/types";

import { useJobs } from "./jobs";
import { useToast } from "./toast";
import { Button, cx, ErrorNote, Icon, Pill, Skeleton, Spinner } from "./ui";

function useDebounced<T>(value: T, delay: number): T {
  const [current, setCurrent] = useState(value);
  useEffect(() => {
    const handle = setTimeout(() => setCurrent(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);
  return current;
}

export function CheckList({ checks, compact = false }: { checks: Check[]; compact?: boolean }) {
  return (
    <ul className={cx("divide-y divide-slate-100 rounded-lg border border-slate-200", compact && "text-xs")}>
      {checks.map((c) => (
        <li key={c.name} className="flex items-start gap-2.5 px-3 py-2">
          <span
            className={cx(
              "mt-0.5 grid size-4 shrink-0 place-items-center rounded-full",
              c.passed ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700",
            )}
          >
            <Icon name={c.passed ? "check" : "x"} className="size-2.5" />
          </span>
          <span className="min-w-0">
            <span className="text-[13px] font-medium text-slate-800">{c.label}</span>
            <span className={cx("block text-xs", c.passed ? "text-slate-500" : "text-rose-700")}>{c.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Editor({ fix }: { fix: FixDetail }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState(fix.after);
  const debounced = useDebounced(text.trim(), 350);
  const dirty = text.trim() !== fix.after.trim();
  const preview = useQuery({
    queryKey: ["check", fix.id, debounced],
    queryFn: () => api.checkText(fix.id, debounced),
    enabled: dirty && debounced.length > 0 && debounced !== fix.after.trim(),
    staleTime: 60_000,
  });
  const checking = preview.isFetching || (dirty && debounced !== text.trim());

  const save = useMutation({
    mutationFn: () => api.editFix(fix.id, text),
    onSuccess: (data) => {
      qc.setQueryData(["fix", fix.id], data);
      void qc.invalidateQueries({ queryKey: ["fixes"] });
      toast({
        tone: data.checks_passed ? "success" : "error",
        title: data.checks_passed ? "Saved. Every check passes" : "Saved, but a check fails",
        body: data.checks_passed ? "Approve it to ship with the next deploy." : "It cannot be approved until it passes.",
      });
    },
    onError: (err) => toast({ tone: "error", title: "Could not save", body: String((err as Error).message) }),
  });

  const field = fix.kind === "set_meta_description" ? "textarea" : "input";
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <label htmlFor="fix-text" className="text-xs font-medium text-slate-500">
          Edit text
        </label>
        <span className="text-xs tabular-nums text-slate-400">{text.trim().length} characters</span>
      </div>
      {field === "textarea" ? (
        <textarea
          id="fix-text"
          value={text}
          rows={3}
          onChange={(e) => setText(e.target.value)}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm leading-relaxed focus:border-slate-900 focus:outline-none"
        />
      ) : (
        <input
          id="fix-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="h-10 w-full rounded-lg border border-slate-300 px-3 text-sm focus:border-slate-900 focus:outline-none"
        />
      )}
      {dirty && (
        <div className="mt-3">
          <div className="mb-1.5 flex items-center gap-2 text-xs font-medium text-slate-500">
            Checks on your edit {checking && <Spinner className="size-3" />}
          </div>
          {preview.data && <CheckList checks={preview.data.checks} compact />}
          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="primary" onClick={() => save.mutate()} loading={save.isPending}>
              Save edit
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setText(fix.after)}>
              Discard
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function FixDrawer({ fixId, onClose }: { fixId: number; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { start, busy } = useJobs();
  const fix = useQuery({ queryKey: ["fix", fixId], queryFn: () => api.fix(fixId) });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const act = useMutation({
    mutationFn: (action: "approve" | "reject") => (action === "approve" ? api.approve(fixId) : api.reject(fixId)),
    onSuccess: (_d, action) => {
      void qc.invalidateQueries({ queryKey: ["fixes"] });
      void qc.invalidateQueries({ queryKey: ["fix", fixId] });
      toast({ tone: "success", title: action === "approve" ? "Approved" : "Rejected" });
    },
    onError: (err) => toast({ tone: "error", title: "Action failed", body: (err as Error).message }),
  });

  const f = fix.data;
  const editable = f && f.source === "model" && ["pending", "needs_review", "approved", "rejected"].includes(f.status);
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button aria-label="Close" className="absolute inset-0 bg-slate-900/20" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        {...(f ? { "aria-labelledby": "fix-drawer-title" } : { "aria-label": "Fix details" })}
        className="relative flex h-full w-[600px] flex-col overflow-hidden border-l border-slate-200 bg-white shadow-2xl">
        {fix.error && (
          <div className="p-6">
            <ErrorNote error={fix.error} />
          </div>
        )}
        {!f ? (
          <div className="space-y-3 p-6">
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
              <div className="min-w-0">
                <div className="text-xs font-medium text-slate-500">
                  {CATEGORY_LABEL[f.category]} · {f.source === "model" ? "Written by the model" : "Rule fix"}
                </div>
                <h2 id="fix-drawer-title" className="mt-0.5 text-lg font-semibold text-slate-900">{KIND_LABEL[f.kind] ?? f.kind}</h2>
                <div className="mt-0.5 truncate font-mono text-xs text-slate-500">
                  {f.path}
                  {f.target && ` · ${f.target}`}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Pill tone={STATUS_TONE[f.status]}>{STATUS_LABEL[f.status]}</Pill>
                <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
                  <Icon name="x" />
                </button>
              </div>
            </div>

            <div className="scrollbar-thin flex-1 space-y-6 overflow-y-auto px-6 py-5">
              <section className="grid grid-cols-2 gap-3">
                <div>
                  <div className="mb-1.5 text-xs font-medium text-slate-500">Before</div>
                  <div className="min-h-16 whitespace-pre-wrap break-words rounded-lg bg-rose-50 px-3 py-2.5 font-mono text-[12px] leading-relaxed text-rose-900 ring-1 ring-inset ring-rose-100">
                    {f.before || "(none)"}
                  </div>
                </div>
                <div>
                  <div className="mb-1.5 text-xs font-medium text-slate-500">After</div>
                  <div className="scrollbar-thin max-h-72 min-h-16 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-emerald-50 px-3 py-2.5 font-mono text-[12px] leading-relaxed text-emerald-900 ring-1 ring-inset ring-emerald-100">
                    {f.after || "(not written yet)"}
                  </div>
                </div>
              </section>

              {f.confidence === "low" && (
                <div className="flex gap-2.5 rounded-lg bg-amber-50 px-3 py-2.5 text-[13px] text-amber-900 ring-1 ring-inset ring-amber-200">
                  <Icon name="alert" className="mt-0.5 size-4 shrink-0" />
                  <span>
                    <span className="font-medium">Low-confidence match, so it waits for a person.</span> {f.confidence_note}
                  </span>
                </div>
              )}
              {f.source === "rule" && f.confidence === "high" && f.confidence_note && (
                <p className="text-[13px] text-slate-600">{f.confidence_note}</p>
              )}
              {f.error && (
                <div className="rounded-lg bg-rose-50 px-3 py-2.5 text-[13px] text-rose-800 ring-1 ring-inset ring-rose-200">
                  {f.error}
                </div>
              )}

              <section>
                <div className="mb-1.5 text-xs font-medium text-slate-500">Checks on the current text</div>
                {f.checks.length ? <CheckList checks={f.checks} /> : <p className="text-sm text-slate-500">No checks yet.</p>}
              </section>

              {editable && <Editor key={f.after + f.updated_at} fix={f} />}

              {f.attempts.length > 0 && (
                <section>
                  <div className="mb-2 text-xs font-medium text-slate-500">Attempts</div>
                  <ol className="space-y-2">
                    {f.attempts.map((a) => (
                      <li key={a.number} className="rounded-lg border border-slate-200 px-3 py-2.5">
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="font-medium text-slate-700">
                            Attempt {a.number} ·{" "}
                            {a.source === "reviewer" ? "Reviewer edit" : a.source === "replay" ? "Model (replayed)" : "Model"}
                          </span>
                          <Pill tone={a.passed ? STATUS_TONE.live : STATUS_TONE.needs_review}>
                            {a.passed ? "Passed" : "Rejected"}
                          </Pill>
                        </div>
                        <p className="text-[13px] text-slate-800">{a.text}</p>
                        {!a.passed && (
                          <ul className="mt-1.5 space-y-0.5">
                            {a.checks
                              .filter((c) => !c.passed)
                              .map((c) => (
                                <li key={c.name} className="text-xs text-rose-700">
                                  {c.label}: {c.detail}
                                </li>
                              ))}
                          </ul>
                        )}
                      </li>
                    ))}
                  </ol>
                </section>
              )}

              {f.session && (
                <section>
                  <div className="mb-2 text-xs font-medium text-slate-500">
                    Model session for this page {f.session.mode === "replay" && "(recorded from a live run)"}
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-center">
                    {[
                      ["Latency", ms(f.session.latency_ms)],
                      ["Tokens in", f.session.input_tokens.toLocaleString()],
                      ["Tokens out", f.session.output_tokens.toLocaleString()],
                      ["Cost", f.session.cost_usd !== null ? `$${f.session.cost_usd.toFixed(4)}` : "-"],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-lg bg-slate-50 px-2 py-2">
                        <div className="text-[11px] text-slate-500">{label}</div>
                        <div className="text-sm font-semibold tabular-nums text-slate-900">{value}</div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-1.5 text-[11px] text-slate-400">
                    {f.session.model} · {f.session.turns} turns
                    {f.session.retries ? ` · ${f.session.retries} retries` : ""}
                  </p>
                </section>
              )}
            </div>

            <div className="flex items-center justify-between gap-2 border-t border-slate-100 px-6 py-4">
              <div className="text-xs text-slate-500">
                {f.approved_by && `Approved by ${f.approved_by === "autopilot" ? "autopilot" : "a reviewer"}`}
              </div>
              <div className="flex gap-2">
                {["live", "verified"].includes(f.status) && (
                  <Button variant="danger" size="sm" disabled={busy} onClick={() => start("Revert", () => api.revert(f.id))}>
                    <Icon name="undo" className="size-3.5" />
                    Revert this fix
                  </Button>
                )}
                {["pending", "needs_review", "approved"].includes(f.status) && (
                  <Button variant="ghost" size="sm" onClick={() => act.mutate("reject")} loading={act.isPending && act.variables === "reject"}>
                    Reject
                  </Button>
                )}
                {["pending", "needs_review", "rejected"].includes(f.status) && (
                  <Button
                    variant="success"
                    size="sm"
                    disabled={!f.checks_passed}
                    title={f.checks_passed ? undefined : "Every check must pass first"}
                    onClick={() => act.mutate("approve")}
                    loading={act.isPending && act.variables === "approve"}
                  >
                    <Icon name="check" className="size-3.5" />
                    Approve
                  </Button>
                )}
              </div>
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
