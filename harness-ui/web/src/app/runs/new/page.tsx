import Link from "next/link";

import { NewRunForm } from "@/components/NewRunForm";

export default function RunsNewPage() {
  return (
    <div className="space-y-6">
      <header>
        <p className="section-label">
          <Link href="/">Home</Link>
          {" / "}
          <Link href="/runs/">runs</Link>
          {" / new"}
        </p>
        <h1 className="page-title">New run</h1>
        <p className="page-lede">
          Defaults come from the harness install. Set the{" "}
          <Link href="/settings/">OpenAI key</Link> first. Project cost →
          approve → start.
        </p>
      </header>
      <NewRunForm />
    </div>
  );
}
