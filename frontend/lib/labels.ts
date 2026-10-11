import type { Category, FixStatus, PolicyMode, RunKind } from "./types";

export const CATEGORY_LABEL: Record<Category, string> = {
  technical: "Technical",
  titles: "Titles",
  meta: "Meta descriptions",
  alt: "Alt text",
  rich: "Rich results",
};

export const CATEGORY_ORDER: Category[] = ["technical", "titles", "meta", "alt", "rich"];

export const CATEGORY_TONE: Record<Category, string> = {
  technical: "bg-sky-50 text-sky-700 ring-sky-200",
  titles: "bg-violet-50 text-violet-700 ring-violet-200",
  meta: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  alt: "bg-amber-50 text-amber-800 ring-amber-200",
  rich: "bg-teal-50 text-teal-700 ring-teal-200",
};

export const CATEGORY_HINT: Record<Category, string> = {
  technical: "Canonicals, broken and redirecting links, extra H1s. Written by rules.",
  titles: "Page titles, written by the model and checked before they can ship.",
  meta: "Meta descriptions, written by the model and checked before they can ship.",
  alt: "Image alt text, written by the model and checked before it can ship.",
  rich: "Social tags and Product structured data, built by rules from the page.",
};

export const POLICY_LABEL: Record<PolicyMode, string> = {
  autopilot: "Autopilot",
  approval: "Approval",
  off: "Off",
};

export const POLICY_HINT: Record<PolicyMode, string> = {
  autopilot: "Passing, confident fixes ship on their own",
  approval: "Every fix waits for a person",
  off: "No fixes are written",
};

export const STATUS_TONE: Record<FixStatus, string> = {
  writing: "bg-slate-100 text-slate-600 ring-slate-200",
  needs_review: "bg-rose-50 text-rose-700 ring-rose-200",
  pending: "bg-amber-50 text-amber-800 ring-amber-200",
  approved: "bg-blue-50 text-blue-700 ring-blue-200",
  rejected: "bg-slate-100 text-slate-500 ring-slate-200",
  live: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  verified: "bg-emerald-600 text-white ring-emerald-600",
  reverted: "bg-slate-100 text-slate-600 ring-slate-300",
};

export const STATUS_LABEL: Record<FixStatus, string> = {
  writing: "Writing",
  needs_review: "Needs review",
  pending: "Waiting for approval",
  approved: "Approved",
  rejected: "Rejected",
  live: "Deployed",
  verified: "Verified live",
  reverted: "Reverted",
};

export const KIND_LABEL: Record<string, string> = {
  set_title: "Title",
  set_meta_description: "Meta description",
  set_alt: "Alt text",
  set_canonical: "Canonical link",
  relink: "Fix link target",
  unlink: "Remove dead link",
  demote_h1: "Extra H1 to H2",
  social: "Social tags",
  product_jsonld: "Product data",
};

export const RULE_LABEL: Record<string, string> = {
  title_missing: "Missing title",
  title_duplicate: "Duplicate title",
  title_too_long: "Title too long",
  meta_missing: "Missing description",
  meta_short: "Short description",
  meta_duplicate: "Duplicate description",
  img_alt_missing: "Image without alt",
  canonical_missing: "Missing canonical",
  link_broken: "Broken link",
  link_redirect: "Link through redirects",
  h1_multiple: "Two H1 headings",
  social_missing: "Missing social tags",
  product_schema_missing: "No Product data",
};

export const RUN_LABEL: Record<RunKind, string> = {
  scan: "Scan",
  generate: "Generate fixes",
  deploy: "Deploy",
  verify: "Verify",
  revert: "Revert",
  rollback: "Rollback",
};

export const SEVERITY_TONE = {
  high: "bg-rose-50 text-rose-700 ring-rose-200",
  medium: "bg-amber-50 text-amber-800 ring-amber-200",
  low: "bg-slate-100 text-slate-600 ring-slate-200",
} as const;

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (value < 1) return `${value.toFixed(2)} ms`;
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

export function clock(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** One line for a fix's new text in a list row. Product data is JSON, so its first line would be just "{". */
export function afterSummary(kind: string, after: string): string {
  if (kind === "product_jsonld") {
    try {
      const data = JSON.parse(after) as {
        name?: string;
        offers?: { price?: string; priceCurrency?: string; availability?: string };
        [key: string]: unknown;
      };
      const parts = [data.name, data.offers?.price && `${data.offers.price} ${data.offers.priceCurrency ?? ""}`.trim()];
      const stock = data.offers?.availability?.split("/").pop();
      if (stock) parts.push(stock === "InStock" ? "in stock" : stock === "OutOfStock" ? "out of stock" : stock);
      const extras = ["sku", "image", "description"].filter((k) => k in data);
      if (extras.length) parts.push(`with ${extras.join(", ")}`);
      return `Product: ${parts.filter(Boolean).join(", ")}`;
    } catch {
      // Not JSON (for example "(name or price not found on the page)"): fall through to the first line.
    }
  }
  return after.split("\n")[0];
}
