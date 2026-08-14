import { RUN_IDS } from "@/lib/staticParams";
import { RunClient } from "./RunClient";

export function generateStaticParams() {
  return RUN_IDS.map((id) => ({ id }));
}

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <RunClient id={id} />;
}
