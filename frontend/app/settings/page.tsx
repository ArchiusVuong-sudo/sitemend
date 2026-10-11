"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useJobs, useSite } from "@/components/jobs";
import { useToast } from "@/components/toast";
import { Button, Card, cx, ErrorNote, Icon, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { CATEGORY_HINT, CATEGORY_LABEL, CATEGORY_ORDER, POLICY_HINT, POLICY_LABEL } from "@/lib/labels";
import type { Category, PolicyMode, SiteInfo } from "@/lib/types";

const MODES: PolicyMode[] = ["autopilot", "approval", "off"];

export default function SettingsPage() {
  const site = useSite();
  if (site.error) return <ErrorNote error={site.error} />;
  if (!site.data) return <Skeleton className="h-96 w-full" />;
  // Remount the form only when the saved values change, so a background refetch never wipes an edit.
  return <SettingsForm key={site.data.custom_instructions + "|" + site.data.never_use_words.join("|")} site={site.data} />;
}

function SettingsForm({ site }: { site: SiteInfo }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { busy } = useJobs();
  const [instructions, setInstructions] = useState(site.custom_instructions);
  const [words, setWords] = useState<string[]>(site.never_use_words);
  const [draft, setDraft] = useState("");

  const save = useMutation({
    mutationFn: () => api.saveSettings({ custom_instructions: instructions, never_use_words: words }),
    onSuccess: (data) => {
      qc.setQueryData(["site"], data);
      toast({ tone: "success", title: "Settings saved", body: "The next Generate fixes run uses them." });
    },
    onError: (err) => toast({ tone: "error", title: "Could not save", body: (err as Error).message }),
  });

  const policy = useMutation({
    mutationFn: ({ category, mode }: { category: Category; mode: PolicyMode }) => api.setPolicy(category, mode),
    onSuccess: (_d, v) => {
      void qc.invalidateQueries({ queryKey: ["site"] });
      toast({ tone: "success", title: `${CATEGORY_LABEL[v.category]}: ${POLICY_LABEL[v.mode]}` });
    },
    onError: (err) => toast({ tone: "error", title: "Could not change the policy", body: (err as Error).message }),
  });

  const reset = useMutation({
    mutationFn: api.reset,
    onSuccess: () => {
      void qc.invalidateQueries();
      toast({ tone: "success", title: "Demo reset", body: "Scans, fixes and releases are cleared." });
    },
    onError: (err) => toast({ tone: "error", title: "Reset failed", body: (err as Error).message }),
  });

  const dirty = instructions !== site.custom_instructions || words.join("|") !== site.never_use_words.join("|");

  const addWord = () => {
    const w = draft.trim().toLowerCase();
    if (w && !words.includes(w)) setWords([...words, w]);
    setDraft("");
  };

  return (
    <div>
      <PageHeader title="Settings" subtitle="What the model is told, what it may never write, and what ships without a person." />
      <div className="grid grid-cols-[1fr_1.1fr] gap-5">
        <Card className="h-fit px-6 py-5">
          <h2 className="text-sm font-semibold text-slate-900">Custom instructions</h2>
          <p className="mb-3 mt-0.5 text-xs text-slate-500">Sent with every model session for this site.</p>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={5}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm leading-relaxed focus:border-slate-900 focus:outline-none"
          />
          <h2 className="mt-5 text-sm font-semibold text-slate-900">Never-use words</h2>
          <p className="mb-3 mt-0.5 text-xs text-slate-500">Text with any of these fails its checks, from the model or a person.</p>
          <div className="flex flex-wrap gap-1.5">
            {words.map((w) => (
              <span key={w} className="inline-flex items-center gap-1 rounded-full bg-slate-100 py-1 pl-3 pr-1.5 text-xs font-medium text-slate-700">
                {w}
                <button
                  aria-label={`Remove ${w}`}
                  onClick={() => setWords(words.filter((x) => x !== w))}
                  className="rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                >
                  <Icon name="x" className="size-3" />
                </button>
              </span>
            ))}
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addWord();
                }
              }}
              onBlur={addWord}
              placeholder="Add a word"
              className="h-7 w-28 rounded-full border border-dashed border-slate-300 px-3 text-xs focus:border-slate-900 focus:outline-none"
            />
          </div>
          <div className="mt-5 flex justify-end">
            <Button variant="primary" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
              Save settings
            </Button>
          </div>
        </Card>

        <Card className="px-6 py-5">
          <h2 className="text-sm font-semibold text-slate-900">Policy per category</h2>
          <p className="mb-4 mt-0.5 text-xs text-slate-500">
            On autopilot, fixes that pass every check ship on their own as a release. A failed check or a low-confidence
            match always waits for a person.
          </p>
          <ul className="divide-y divide-slate-100">
            {CATEGORY_ORDER.map((c) => {
              const mode = site.policies[c];
              return (
                <li key={c} className="flex items-center justify-between gap-4 py-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-800">{CATEGORY_LABEL[c]}</div>
                    <div className="text-xs text-slate-500">{CATEGORY_HINT[c]}</div>
                  </div>
                  <div className="flex shrink-0 rounded-lg bg-slate-100 p-0.5" role="radiogroup" aria-label={CATEGORY_LABEL[c]}>
                    {MODES.map((m) => (
                      <button
                        key={m}
                        role="radio"
                        aria-checked={mode === m}
                        title={POLICY_HINT[m]}
                        disabled={policy.isPending}
                        onClick={() => mode !== m && policy.mutate({ category: c, mode: m })}
                        className={cx(
                          "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                          mode === m
                            ? m === "autopilot"
                              ? "bg-emerald-600 text-white shadow-xs"
                              : m === "approval"
                                ? "bg-white text-slate-900 shadow-xs"
                                : "bg-slate-500 text-white"
                            : "text-slate-500 hover:text-slate-800",
                        )}
                      >
                        {POLICY_LABEL[m]}
                      </button>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      <Card className="mt-5 flex items-center justify-between px-6 py-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Reset the demo</h2>
          <p className="text-xs text-slate-500">Clears scans, fixes, releases and traces, and restores the default settings.</p>
        </div>
        <Button
          variant="danger"
          loading={reset.isPending}
          title={busy ? "Also clears the job that is running" : undefined}
          onClick={() => reset.mutate()}
        >
          Reset demo
        </Button>
      </Card>
    </div>
  );
}
