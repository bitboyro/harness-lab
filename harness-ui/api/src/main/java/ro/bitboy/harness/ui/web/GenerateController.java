package ro.bitboy.harness.ui.web;

import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.ArtifactRef;
import ro.bitboy.harness.ui.dto.CreateExperimentFromGenerateRequest;
import ro.bitboy.harness.ui.dto.ExperimentRef;
import ro.bitboy.harness.ui.dto.GenerateJob;
import ro.bitboy.harness.ui.dto.GenerateProgress;
import ro.bitboy.harness.ui.dto.StartGenerateRequest;
import ro.bitboy.harness.ui.service.GenerateService;

@RestController
@RequestMapping("/api/v1/generate")
public class GenerateController {

  private final GenerateService generate;

  public GenerateController(GenerateService generate) {
    this.generate = generate;
  }

  @PostMapping
  @ResponseStatus(HttpStatus.ACCEPTED)
  @Operation(operationId = Capabilities.START_GENERATE)
  public GenerateJob start(@Valid @RequestBody StartGenerateRequest body) {
    return generate.start(body);
  }

  @GetMapping("/{jobId}/progress")
  @Operation(operationId = Capabilities.GET_GENERATE_PROGRESS)
  public GenerateProgress progress(@PathVariable String jobId) {
    return generate.progress(jobId);
  }

  @GetMapping("/{jobId}/manifest")
  @Operation(operationId = Capabilities.GET_GENERATE_MANIFEST)
  public JsonNode manifest(@PathVariable String jobId) {
    return generate.manifest(jobId);
  }

  @GetMapping("/{jobId}/artifacts")
  @Operation(operationId = Capabilities.LIST_GENERATE_ARTIFACTS)
  public List<ArtifactRef> listArtifacts(@PathVariable String jobId) {
    return generate.listArtifacts(jobId);
  }

  @GetMapping("/{jobId}/artifacts/{*name}")
  @Operation(operationId = Capabilities.GET_GENERATE_ARTIFACT)
  public ResponseEntity<Resource> getArtifact(
      @PathVariable String jobId,
      @PathVariable String name) {
    return generate.getArtifact(jobId, name.startsWith("/") ? name.substring(1) : name);
  }

  @PostMapping("/{jobId}/experiment")
  @ResponseStatus(HttpStatus.CREATED)
  @Operation(operationId = Capabilities.CREATE_EXPERIMENT_FROM_GENERATE)
  public ExperimentRef createExperiment(
      @PathVariable String jobId,
      @Valid @RequestBody CreateExperimentFromGenerateRequest body) {
    return generate.createExperiment(jobId, body);
  }
}
