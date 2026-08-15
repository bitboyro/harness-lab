import { RunsHubClient } from "./RunsHubClient";

export default function RunsIndexPage() {
  return (
    <div>
      <p className="section-label">Results</p>
      <h1 className="page-title">Runs</h1>
      <p className="page-lede">
        Browse finished and in-flight matrices, open reports and transcripts.
      </p>
      <RunsHubClient />
    </div>
  );
}
