export type Category = "technical" | "titles" | "meta" | "alt" | "rich";
export type PolicyMode = "autopilot" | "approval" | "off";
export type RunKind = "scan" | "generate" | "deploy" | "verify" | "revert" | "rollback";
export type RunStatus = "queued" | "running" | "done" | "failed";
export type FixStatus =
  | "writing"
  | "needs_review"
  | "pending"
  | "approved"
  | "rejected"
  | "live"
  | "verified"
  | "reverted";

export interface Grade {
  site: number;
  technical: number;
  onpage: number;
  rich: number;
  clean_pages: number;
  pages: number;
  issues: number;
}

export interface RunSummary {
  grade?: Grade;
  grade_before?: Grade;
  categories?: Partial<Record<Category, number>>;
  pages?: number;
  fetches?: number;
  release?: string | null;
  issues_fixed?: number;
  issues_open?: number;
  verified?: number;
  still_open?: number;
  rule_fixes?: number;
  model_pages?: number;
  fixes?: number;
  autopilot?: number;
  waiting?: number;
  needs_review?: number;
  llm_mode?: string;
  model?: string;
  ops?: number;
  rolled_back_to?: string;
  reverted_fix?: number;
}

export interface Run {
  id: number;
  kind: RunKind;
  status: RunStatus;
  target: "origin" | "edge";
  total: number;
  done: number;
  summary: RunSummary;
  error: string;
  release: string | null;
  llm_mode: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface Span {
  id: number;
  parent: number | null;
  name: string;
  kind: "task" | "fetch" | "model" | "tool" | "step";
  label: string;
  started_at: string;
  duration_ms: number;
  status: "ok" | "error" | "running";
  retries: number;
  error: string;
  attrs: Record<string, unknown>;
}

export interface ModelSession {
  path: string;
  mode: "live" | "replay";
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  turns: number;
  retries: number;
  error: string;
  created_at: string;
}

export interface RunDetail extends Run {
  spans: Span[];
  sessions: ModelSession[];
}

export interface Baseline {
  name: string;
  kind: Span["kind"];
  count: number;
  p50_ms: number;
  p95_ms: number;
  errors: number;
  retries: number;
}

export interface LlmInfo {
  mode: "live" | "replay";
  reason: string;
  model: string;
}

export interface SiteInfo {
  name: string;
  domain: string;
  custom_instructions: string;
  never_use_words: string[];
  policies: Record<Category, PolicyMode>;
  categories: { id: Category; label: string }[];
  active_release: string | null;
  latest_scan: Run | null;
  first_scan_grade: Grade | null;
  latest_edge_scan: Run | null;
  running: Run | null;
  llm: LlmInfo;
}

export interface Issue {
  id: number;
  path: string;
  rule: string;
  key: string;
  category: Category;
  severity: "high" | "medium" | "low";
  message: string;
  evidence: string;
  priority: number;
  priority_reason: string;
  fingerprint: string;
  fix: { id: number; status: FixStatus; status_label: string } | null;
}

export interface Check {
  name: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface Attempt {
  number: number;
  source: "model" | "replay" | "reviewer";
  text: string;
  passed: boolean;
  checks: Check[];
  created_at: string;
}

export interface Fix {
  id: number;
  path: string;
  category: Category;
  kind: string;
  target: string;
  rules: string[];
  source: "rule" | "model";
  before: string;
  after: string;
  op: Record<string, unknown>;
  status: FixStatus;
  status_label: string;
  confidence: "high" | "low";
  confidence_note: string;
  checks: Check[];
  checks_passed: boolean;
  approved_by: string;
  error: string;
  attempts_count: number;
  created_run: number | null;
  verified_run: number | null;
  updated_at: string;
}

export interface FixDetail extends Fix {
  attempts: Attempt[];
  session: ModelSession | null;
}

export interface ReleaseOp {
  fix_id: number;
  path: string;
  category: Category;
  op: Record<string, unknown>;
  fix: { kind: string; status: FixStatus; after: string; source: string; target: string } | null;
}

export interface Release {
  id: number;
  number: number;
  label: string;
  kind: "autopilot" | "deploy" | "revert" | "rollback";
  note: string;
  parent_label: string | null;
  ops: ReleaseOp[];
  created_at: string;
  active: boolean;
}

export interface CompareRow {
  type: "same" | "added" | "removed";
  old: number | null;
  new: number | null;
  text: string;
}

export interface Compare {
  path: string;
  release: string;
  identical: boolean;
  added: number;
  removed: number;
  rows: CompareRow[];
}
