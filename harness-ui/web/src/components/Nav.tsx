import Link from "next/link";
import { isMockMode } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/targets/", label: "Targets" },
  { href: "/runs/new/", label: "New run" },
  { href: "/compare/", label: "Compare" },
];

export function Nav() {
  return (
    <header className="border-b border-zinc-300 bg-zinc-100">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-4 py-3">
        <Link href="/" className="font-semibold tracking-tight text-zinc-900">
          harness-ui
        </Link>
        <nav className="flex flex-wrap gap-3 text-sm">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-zinc-700 underline-offset-2 hover:underline"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        {isMockMode() && (
          <span className="ml-auto rounded border border-amber-600 bg-amber-50 px-2 py-0.5 text-xs text-amber-900">
            MOCK
          </span>
        )}
      </div>
    </header>
  );
}
