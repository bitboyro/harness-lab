import Link from "next/link";
import { ResourceJump } from "@/components/ResourceJump";
import { isMockMode } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/experiments/", label: "Experiments" },
  { href: "/runs/", label: "Runs" },
  { href: "/targets/", label: "Targets" },
  { href: "/packs/", label: "Packs" },
  { href: "/settings/", label: "Settings" },
];

export function Nav() {
  return (
    <header className="topbar">
      <Link href="/" className="brand">
        harness<span>-lab</span>
      </Link>
      <nav className="topnav">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href}>
            {l.label}
          </Link>
        ))}
      </nav>
      <ResourceJump />
      {isMockMode() ? (
        <span className="badge-mock">Mock</span>
      ) : (
        <span className="topnav" style={{ color: "var(--muted)" }}>
          Local · :8085
        </span>
      )}
    </header>
  );
}
