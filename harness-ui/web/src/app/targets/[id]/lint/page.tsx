import { TARGET_IDS } from "@/lib/staticParams";
import { LintClient } from "./LintClient";

export function generateStaticParams() {
  return TARGET_IDS.map((id) => ({ id }));
}

export default async function LintPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <LintClient id={id} />;
}
