import { PACK_IDS } from "@/lib/staticParams";
import { PackClient } from "./PackClient";

export function generateStaticParams() {
  return PACK_IDS.map((id) => ({ id }));
}

export default async function PackPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PackClient id={id} />;
}
