import { EXPERIMENT_IDS, staticParamsFromIds } from "@/lib/staticParams";

import { ExperimentClient } from "./ExperimentClient";

export function generateStaticParams() {
  return staticParamsFromIds(EXPERIMENT_IDS);
}

export default async function ExperimentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ExperimentClient id={id} />;
}
