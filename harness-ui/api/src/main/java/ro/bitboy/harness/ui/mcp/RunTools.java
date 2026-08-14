package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import org.springframework.core.io.Resource;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.ArtifactRef;
import ro.bitboy.harness.ui.dto.CostProjection;
import ro.bitboy.harness.ui.dto.ProgressEnvelope;
import ro.bitboy.harness.ui.dto.RunJob;
import ro.bitboy.harness.ui.dto.RunRequest;
import ro.bitboy.harness.ui.dto.RunSummary;
import ro.bitboy.harness.ui.dto.TranscriptResponse;
import ro.bitboy.harness.ui.service.ArtifactService;
import ro.bitboy.harness.ui.service.RunService;

@Component
public class RunTools {

  private final RunService runs;
  private final ArtifactService artifacts;

  public RunTools(RunService runs, ArtifactService artifacts) {
    this.runs = runs;
    this.artifacts = artifacts;
  }

  @Tool(name = Capabilities.PROJECT_RUN_COST, description = "Dry-run cost projection for a matrix.")
  public CostProjection projectRunCost(RunRequest body) {
    return runs.project(body);
  }

  @Tool(name = Capabilities.START_RUN, description = "Start a harness run (approve must be true).")
  public RunJob startRun(RunRequest body) {
    return runs.start(body);
  }

  @Tool(name = Capabilities.LIST_RUNS, description = "List results directories.")
  public List<RunSummary> listRuns() {
    return runs.list();
  }

  @Tool(name = Capabilities.DELETE_RUN, description = "Delete a run directory and job metadata.")
  public void deleteRun(String id) {
    runs.delete(id);
  }

  @Tool(name = Capabilities.GET_RUN_PROGRESS, description = "Poll run progress and job status.")
  public ProgressEnvelope getRunProgress(String id) {
    return runs.progress(id);
  }

  @Tool(name = Capabilities.GET_REPORT, description = "Read adapter report JSON for a run.")
  public JsonNode getReport(String id) {
    return runs.report(id);
  }

  @Tool(name = Capabilities.GET_ANALYSIS,
      description = "Deep-dive analysis tables for a finished run (optional only=comma keys).")
  public JsonNode getAnalysis(String id, String only) {
    return runs.analysis(id, only);
  }

  @Tool(name = Capabilities.GET_BRIEF, description = "Read adapter brief JSON for a run.")
  public JsonNode getBrief(String id) {
    return runs.brief(id);
  }

  @Tool(name = Capabilities.GET_TRANSCRIPT, description = "Fetch one cell transcript.")
  public TranscriptResponse getTranscript(String id, String arm, String taskId, int repeat) {
    return runs.transcript(id, arm, taskId, repeat, false);
  }

  @Tool(name = Capabilities.LIST_ARTIFACTS, description = "List rendered artifacts for a run.")
  public List<ArtifactRef> listArtifacts(String id) {
    return artifacts.list(id);
  }

  @Tool(name = Capabilities.GET_ARTIFACT, description = "Fetch one artifact (base64-encoded body).")
  public Map<String, Object> getArtifact(String id, String name) throws Exception {
    ResponseEntity<Resource> resp = artifacts.get(id, name);
    Resource body = resp.getBody();
    byte[] bytes = body == null ? new byte[0] : body.getInputStream().readAllBytes();
    String contentType =
        resp.getHeaders().getContentType() == null
            ? "application/octet-stream"
            : resp.getHeaders().getContentType().toString();
    return Map.of(
        "name", name,
        "contentType", contentType,
        "contentBase64", Base64.getEncoder().encodeToString(bytes));
  }

  @Tool(name = Capabilities.PUT_ARTIFACT, description = "Write an artifact (content_base64 or text body).")
  public ArtifactRef putArtifact(String id, String name, JsonNode args) {
    byte[] bytes;
    if (args != null && args.hasNonNull("content_base64")) {
      bytes = Base64.getDecoder().decode(args.get("content_base64").asText());
    } else if (args != null && args.hasNonNull("text")) {
      bytes = args.get("text").asText("").getBytes(StandardCharsets.UTF_8);
    } else {
      bytes = new byte[0];
    }
    return artifacts.put(id, name, new ByteArrayInputStream(bytes));
  }
}
