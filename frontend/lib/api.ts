import type {
  Baseline,
  Category,
  Check,
  Compare,
  Fix,
  FixDetail,
  Issue,
  PolicyMode,
  Release,
  Run,
  RunDetail,
  SiteInfo,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("The API is not reachable. Is the backend running?", 0);
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const message =
      (body && typeof body === "object" && "error" in body && String(body.error)) ||
      (body && typeof body === "object" && JSON.stringify(body)) ||
      `Request failed (${res.status})`;
    throw new ApiError(message, res.status);
  }
  return body as T;
}

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export interface Started {
  run_id: number;
  status: string;
}

export const api = {
  site: () => request<SiteInfo>("/api/site"),
  saveSettings: (data: { custom_instructions?: string; never_use_words?: string[] }) =>
    request<SiteInfo>("/api/site", { method: "PATCH", body: JSON.stringify(data) }),
  setPolicy: (category: Category, mode: PolicyMode) =>
    request<Record<Category, PolicyMode>>(`/api/policies/${category}`, {
      method: "PUT",
      body: JSON.stringify({ mode }),
    }),
  reset: () => post<SiteInfo>("/api/site/reset"),
  scan: () => post<Started>("/api/scan"),
  generate: () => post<Started>("/api/generate"),
  deploy: () => post<Started>("/api/deploy"),
  verify: () => post<Started>("/api/verify"),
  revert: (fixId: number) => post<Started>(`/api/fixes/${fixId}/revert`),
  rollback: (number: number) => post<Started>(`/api/releases/${number}/rollback`),
  run: (id: number) => request<Run>(`/api/runs/${id}`),
  runDetail: (id: number) => request<RunDetail>(`/api/runs/${id}?spans=1`),
  runs: () => request<Run[]>("/api/runs"),
  baselines: () => request<Baseline[]>("/api/baselines"),
  issues: (target: "origin" | "edge") =>
    request<{ run: Run | null; issues: Issue[] }>(`/api/issues?target=${target}`),
  pages: () => request<{ path: string; title: string }[]>("/api/pages"),
  fixes: () => request<Fix[]>("/api/fixes"),
  fix: (id: number) => request<FixDetail>(`/api/fixes/${id}`),
  editFix: (id: number, text: string) =>
    request<FixDetail>(`/api/fixes/${id}`, { method: "PATCH", body: JSON.stringify({ text }) }),
  checkText: (id: number, text: string) =>
    post<{ checks: Check[]; passed: boolean }>(`/api/fixes/${id}/check`, { text }),
  approve: (id: number) => post<Fix>(`/api/fixes/${id}/approve`),
  reject: (id: number) => post<Fix>(`/api/fixes/${id}/reject`),
  bulkApprove: (category: Category) => post<{ approved: number[] }>("/api/fixes/bulk-approve", { category }),
  releases: () => request<Release[]>("/api/releases"),
  compare: (path: string) => request<Compare>(`/api/compare?path=${encodeURIComponent(path)}`),
};
