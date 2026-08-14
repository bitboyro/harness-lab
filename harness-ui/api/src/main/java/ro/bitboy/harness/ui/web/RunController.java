package ro.bitboy.harness.ui.web;

import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
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
import ro.bitboy.harness.ui.dto.ArtifactRef;
import ro.bitboy.harness.ui.dto.CellRef;
import ro.bitboy.harness.ui.dto.CostProjection;
import ro.bitboy.harness.ui.dto.ProgressEnvelope;
import ro.bitboy.harness.ui.dto.RunJob;
import ro.bitboy.harness.ui.dto.RunRequest;
import ro.bitboy.harness.ui.dto.RunSummary;
import ro.bitboy.harness.ui.dto.TranscriptResponse;
import ro.bitboy.harness.ui.service.ArtifactService;
import ro.bitboy.harness.ui.service.RunService;

@RestController
@RequestMapping("/api/v1/runs")
public class RunController {

  private final RunService runs;
  private final ArtifactService artifacts;

  public RunController(RunService runs, ArtifactService artifacts) {
    this.runs = runs;
    this.artifacts = artifacts;
  }

  @PostMapping("/project")
  @Operation(operationId = Capabilities.PROJECT_RUN_COST)
  public CostProjection project(@Valid @RequestBody RunRequest body) {
    return runs.project(body);
  }

  @PostMapping
  @ResponseStatus(HttpStatus.ACCEPTED)
  @Operation(operationId = Capabilities.START_RUN)
  public RunJob start(@Valid @RequestBody RunRequest body) {
    return runs.start(body);
  }

  @GetMapping
  @Operation(operationId = Capabilities.LIST_RUNS)
  public List<RunSummary> list() {
    return runs.list();
  }

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  @Operation(operationId = Capabilities.DELETE_RUN)
  public void delete(@PathVariable String id) {
    runs.delete(id);
  }

  @GetMapping("/{id}/progress")
  @Operation(operationId = Capabilities.GET_RUN_PROGRESS)
  public ProgressEnvelope progress(@PathVariable String id) {
    return runs.progress(id);
  }

  @GetMapping("/{id}/report")
  @Operation(operationId = Capabilities.GET_REPORT)
  public JsonNode report(@PathVariable String id) {
    return runs.report(id);
  }

  @GetMapping("/{id}/analysis")
  @Operation(operationId = Capabilities.GET_ANALYSIS)
  public JsonNode analysis(
      @PathVariable String id,
      @RequestParam(required = false) String only) {
    return runs.analysis(id, only);
  }

  @GetMapping("/{id}/brief")
  @Operation(operationId = Capabilities.GET_BRIEF)
  public JsonNode brief(@PathVariable String id) {
    return runs.brief(id);
  }

  @GetMapping("/{id}/cells")
  public List<CellRef> cells(@PathVariable String id) {
    return runs.listCells(id);
  }

  @GetMapping("/{id}/transcripts/{arm}/{taskId}/{repeat}")
  @Operation(operationId = Capabilities.GET_TRANSCRIPT)
  public TranscriptResponse transcript(
      @PathVariable String id,
      @PathVariable String arm,
      @PathVariable String taskId,
      @PathVariable int repeat,
      @RequestParam(defaultValue = "false") boolean verbose) {
    return runs.transcript(id, arm, taskId, repeat, verbose);
  }

  @GetMapping("/{id}/artifacts")
  @Operation(operationId = Capabilities.LIST_ARTIFACTS)
  public List<ArtifactRef> listArtifacts(@PathVariable String id) {
    return artifacts.list(id);
  }

  @GetMapping("/{id}/artifacts/{*name}")
  @Operation(operationId = Capabilities.GET_ARTIFACT)
  public ResponseEntity<Resource> getArtifact(
      @PathVariable String id,
      @PathVariable("name") String name) {
    String cleaned = name.startsWith("/") ? name.substring(1) : name;
    return artifacts.get(id, cleaned);
  }

  @PutMapping("/{id}/artifacts/{*name}")
  @ResponseStatus(HttpStatus.CREATED)
  @Operation(operationId = Capabilities.PUT_ARTIFACT)
  public ArtifactRef putArtifact(
      @PathVariable String id,
      @PathVariable("name") String name,
      @RequestBody byte[] body) {
    String cleaned = name.startsWith("/") ? name.substring(1) : name;
    return artifacts.put(id, cleaned, new java.io.ByteArrayInputStream(body == null ? new byte[0] : body));
  }
}
