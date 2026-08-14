"use client";

import Link from "next/link";
import { ArmsMatrix } from "@/components/ArmsMatrix";

export default function HomePage() {
  return (
    <div className="space-y-12">
      <section className="hero-home">
        <h1>Evaluate your API packaging</h1>
        <p className="page-lede" style={{ marginTop: "1rem" }}>
          Same API and tasks. Different packaging (MCP, docs, skill). See which
          one the agent uses better.
        </p>
        <div className="cta-row">
          <Link href="/experiments/new/from-openapi/" className="btn btn-primary">
            Start from OpenAPI spec
          </Link>
          <Link href="/runs/new/" className="btn btn-ghost">
            Quick run
          </Link>
          <Link href="/experiments/new/" className="btn btn-ghost">
            New experiment
          </Link>
        </div>
      </section>

      <ArmsMatrix />
    </div>
  );
}
