import { cx } from "./ui";

function tone(score: number): { ring: string; text: string; bar: string } {
  if (score >= 90) return { ring: "stroke-emerald-500", text: "text-emerald-600", bar: "bg-emerald-500" };
  if (score >= 75) return { ring: "stroke-amber-500", text: "text-amber-600", bar: "bg-amber-500" };
  return { ring: "stroke-rose-500", text: "text-rose-600", bar: "bg-rose-500" };
}

export function GradeRing({ score, size = 148, label = "Site grade" }: { score: number; size?: number; label?: string }) {
  const r = 58;
  const c = 2 * Math.PI * r;
  const t = tone(score);
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox="0 0 140 140" className="size-full -rotate-90">
        <circle cx="70" cy="70" r={r} className="fill-none stroke-slate-100" strokeWidth="12" />
        <circle
          cx="70"
          cy="70"
          r={r}
          className={cx("fill-none transition-[stroke-dashoffset] duration-700", t.ring)}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - score / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cx("text-4xl font-semibold tabular-nums tracking-tight", t.text)}>{score}</span>
        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</span>
      </div>
    </div>
  );
}

export function ScoreBar({ label, score, before }: { label: string; score: number; before?: number }) {
  const t = tone(score);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-sm">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="tabular-nums text-slate-900">
          {before !== undefined && before !== score && <span className="mr-1.5 text-slate-400">{before} to</span>}
          <span className="font-semibold">{score}</span>
          <span className="text-slate-400">/100</span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={cx("h-full rounded-full transition-[width] duration-700", t.bar)} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-4 py-3">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-400">{hint}</div>}
    </div>
  );
}
