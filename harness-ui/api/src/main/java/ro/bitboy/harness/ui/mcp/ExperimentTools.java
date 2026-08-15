package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;
import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.AddExperimentArmsRequest;
import ro.bitboy.harness.ui.dto.CreateExperimentRequest;
import ro.bitboy.harness.ui.dto.ExperimentRef;
import ro.bitboy.harness.ui.dto.ExperimentRunProjection;
import ro.bitboy.harness.ui.dto.ExperimentRunRequest;
import ro.bitboy.harness.ui.dto.ExperimentSummary;
import ro.bitboy.harness.ui.dto.ReportSnapshotRef;
import ro.bitboy.harness.ui.dto.RunJob;
import ro.bitboy.harness.ui.dto.UpdateExperimentRequest;
import ro.bitboy.harness.ui.service.ExperimentService;

@Component
public class ExperimentTools {

  private final ExperimentService experiments;

  public ExperimentTools(ExperimentService experiments) {
    this.experiments = experiments;
  }

  @Tool(name = Capabilities.LIST_EXPERIMENTS, description = "List experiment sidecars under /data/results.")
  public List<ExperimentSummary> listExperiments(boolean all) {
    return experiments.list(all);
  }

  @Tool(name = Capabilities.CREATE_EXPERIMENT, description = "Create an experiment sidecar from YAML or planPath.")
  public ExperimentRef createExperiment(CreateExperimentRequest body) {
    return experiments.create(body);
  }

  @Tool(name = Capabilities.GET_EXPERIMENT, description = "Read experiment sidecar + adapter envelope.")
  public JsonNode getExperiment(String id, String slice) {
    return experiments.get(id, slice);
  }

  @Tool(name = Capabilities.UPDATE_EXPERIMENT, description = "Replace draft experiment YAML.")
  public ExperimentRef updateExperiment(String id, UpdateExperimentRequest body) {
    return experiments.update(id, body);
  }

  @Tool(name = Capabilities.ADD_EXPERIMENT_ARMS, description = "Append presets to run_plan.include.presets.")
  public ExperimentRef addExperimentArms(String id, AddExperimentArmsRequest body) {
    return experiments.addArms(id, body);
  }

  @Tool(name = Capabilities.PROJECT_EXPERIMENT_RUN, description = "Dry-run cost for missing experiment cells.")
  public ExperimentRunProjection projectExperimentRun(String id, ExperimentRunRequest body) {
    return experiments.project(
        id, body == null ? new ExperimentRunRequest(null, null, null, null) : body);
  }

  @Tool(name = Capabilities.START_EXPERIMENT_RUN, description = "Start run for missing experiment cells.")
  public RunJob startExperimentRun(String id, ExperimentRunRequest body) {
    return experiments.start(
        id, body == null ? new ExperimentRunRequest(null, null, null, null) : body);
  }

  @Tool(name = Capabilities.GET_EXPERIMENT_COVERAGE, description = "Adapter coverage counts for an experiment.")
  public JsonNode getExperimentCoverage(String id, String slice) {
    return experiments.coverage(id, slice);
  }

  @Tool(name = Capabilities.LIST_EXPERIMENT_REPORTS, description = "List dated report snapshots.")
  public List<ReportSnapshotRef> listExperimentReports(String id) {
    return experiments.listReports(id);
  }

  @Tool(name = Capabilities.SNAPSHOT_EXPERIMENT_REPORT, description = "Freeze current report JSON to reports/.")
  public ReportSnapshotRef snapshotExperimentReport(String id) {
    return experiments.snapshot(id);
  }

  @Tool(name = Capabilities.DELETE_EXPERIMENT, description = "Delete an experiment sidecar and its results directory.")
  public void deleteExperiment(String id) {
    experiments.delete(id);
  }
}
