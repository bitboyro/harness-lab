import { TARGET_IDS } from "@/lib/staticParams";
import { TargetClient } from "./TargetClient";

export function generateStaticParams() {
  return TARGET_IDS.map((id) => ({ id }));
}

export default async function TargetPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <TargetClient id={id} />;
}
