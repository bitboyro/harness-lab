import { ExperimentListClient } from "./ExperimentListClient";

export default function ExperimentsIndexPage() {
  return (
    <div>
      <p className="section-label">Experiments</p>
      <h1 className="page-title">Declared matrices</h1>
      <p className="page-lede">
        Sidecar-backed runs with additive arms and missing-cell scheduling.
      </p>
      <ExperimentListClient />
    </div>
  );
}
