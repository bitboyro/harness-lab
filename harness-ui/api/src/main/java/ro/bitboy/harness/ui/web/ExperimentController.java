package ro.bitboy.harness.ui.web;

import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
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

@RestController
@RequestMapping("/api/v1/experiments")
public class ExperimentController {

  private final ExperimentService experiments;

  public ExperimentController(ExperimentService experiments) {
    this.experiments = experiments;
  }

  @GetMapping
  @Operation(operationId = Capabilities.LIST_EXPERIMENTS)
  public List<ExperimentSummary> list(@RequestParam(defaultValue = "false") boolean all) {
    return experiments.list(all);
  }

  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  @Operation(operationId = Capabilities.CREATE_EXPERIMENT)
  public ExperimentRef create(@Valid @RequestBody CreateExperimentRequest body) {
    return experiments.create(body);
  }

  @GetMapping("/{id}")
  @Operation(operationId = Capabilities.GET_EXPERIMENT)
  public JsonNode get(@PathVariable String id, @RequestParam(required = false) String slice) {
    return experiments.get(id, slice);
  }

  @PutMapping("/{id}")
  @Operation(operationId = Capabilities.UPDATE_EXPERIMENT)
  public ExperimentRef update(
      @PathVariable String id,
      @Valid @RequestBody UpdateExperimentRequest body) {
    return experiments.update(id, body);
  }

  @PostMapping("/{id}/arms")
  @Operation(operationId = Capabilities.ADD_EXPERIMENT_ARMS)
  public ExperimentRef addArms(
      @PathVariable String id,
      @Valid @RequestBody AddExperimentArmsRequest body) {
    return experiments.addArms(id, body);
  }

  @PostMapping("/{id}/run/project")
  @Operation(operationId = Capabilities.PROJECT_EXPERIMENT_RUN)
  public ExperimentRunProjection project(
      @PathVariable String id,
      @RequestBody ExperimentRunRequest body) {
    return experiments.project(id, body == null ? new ExperimentRunRequest(null, null, null, null) : body);
  }

  @PostMapping("/{id}/run")
  @ResponseStatus(HttpStatus.ACCEPTED)
  @Operation(operationId = Capabilities.START_EXPERIMENT_RUN)
  public RunJob start(
      @PathVariable String id,
      @RequestBody ExperimentRunRequest body) {
    return experiments.start(id, body == null ? new ExperimentRunRequest(null, null, null, null) : body);
  }

  @GetMapping("/{id}/coverage")
  @Operation(operationId = Capabilities.GET_EXPERIMENT_COVERAGE)
  public JsonNode coverage(
      @PathVariable String id,
      @RequestParam(required = false) String slice) {
    return experiments.coverage(id, slice);
  }

  @GetMapping("/{id}/reports")
  @Operation(operationId = Capabilities.LIST_EXPERIMENT_REPORTS)
  public List<ReportSnapshotRef> listReports(@PathVariable String id) {
    return experiments.listReports(id);
  }

  @PostMapping("/{id}/reports/snapshot")
  @ResponseStatus(HttpStatus.CREATED)
  @Operation(operationId = Capabilities.SNAPSHOT_EXPERIMENT_REPORT)
  public ReportSnapshotRef snapshot(@PathVariable String id) {
    return experiments.snapshot(id);
  }

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  @Operation(operationId = Capabilities.DELETE_EXPERIMENT)
  public void delete(@PathVariable String id) {
    experiments.delete(id);
  }
}
