import { ARTIFACT_NAMES, RUN_IDS } from "@/lib/staticParams";
import { ArtifactClient } from "./ArtifactClient";

export function generateStaticParams() {
  const params: { id: string; name: string }[] = [];
  for (const id of RUN_IDS) {
    for (const name of ARTIFACT_NAMES) {
      params.push({ id, name });
    }
  }
  return params;
}

export default async function ArtifactPage({
  params,
}: {
  params: Promise<{ id: string; name: string }>;
}) {
  const { id, name } = await params;
  return <ArtifactClient runId={id} name={name} />;
}
