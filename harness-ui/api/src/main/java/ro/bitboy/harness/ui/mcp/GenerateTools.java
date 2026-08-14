package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import org.springframework.core.io.Resource;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.ArtifactRef;
import ro.bitboy.harness.ui.dto.CreateExperimentFromGenerateRequest;
import ro.bitboy.harness.ui.dto.ExperimentRef;
import ro.bitboy.harness.ui.dto.GenerateJob;
import ro.bitboy.harness.ui.dto.GenerateProgress;
import ro.bitboy.harness.ui.dto.StartGenerateRequest;
import ro.bitboy.harness.ui.service.GenerateService;

@Component
public class GenerateTools {

  private final GenerateService generate;

  public GenerateTools(GenerateService generate) {
    this.generate = generate;
  }

  @Tool(name = Capabilities.START_GENERATE, description = "Start OpenAPI onboarding generate job.")
  public GenerateJob startGenerate(StartGenerateRequest body) {
    return generate.start(body);
  }

  @Tool(name = Capabilities.GET_GENERATE_PROGRESS, description = "Poll generate job progress.")
  public GenerateProgress getGenerateProgress(String jobId) {
    return generate.progress(jobId);
  }

  @Tool(name = Capabilities.GET_GENERATE_MANIFEST, description = "Read generate manifest when complete.")
  public JsonNode getGenerateManifest(String jobId) {
    return generate.manifest(jobId);
  }

  @Tool(name = Capabilities.LIST_GENERATE_ARTIFACTS, description = "List files in generate workspace.")
  public List<ArtifactRef> listGenerateArtifacts(String jobId) {
    return generate.listArtifacts(jobId);
  }

  @Tool(name = Capabilities.GET_GENERATE_ARTIFACT, description = "Fetch one generate workspace file (base64).")
  public Map<String, Object> getGenerateArtifact(String jobId, String name) throws Exception {
    ResponseEntity<Resource> resp = generate.getArtifact(jobId, name);
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

  @Tool(name = Capabilities.CREATE_EXPERIMENT_FROM_GENERATE,
      description = "Create field experiment from completed generate job.")
  public ExperimentRef createExperimentFromGenerate(
      String jobId,
      CreateExperimentFromGenerateRequest body) {
    return generate.createExperiment(jobId, body);
  }
}
