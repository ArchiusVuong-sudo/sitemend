import Link from "next/link";

import { Empty } from "@/components/ui";

export default function NotFound() {
  return (
    <Empty
      title="Page not found"
      body="This address is not part of the dashboard."
      action={
        <Link
          href="/"
          className="inline-flex items-center rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          Back to Overview
        </Link>
      }
    />
  );
}
