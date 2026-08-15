package ro.bitboy.harness.ui.web;

import org.springframework.core.io.Resource;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import ro.bitboy.harness.ui.service.ArtifactService;

/** Same files as get_artifact, for iframe embeds under {@code /artifacts/{runId}/**}. */
@RestController
public class PublicArtifactController {

  private final ArtifactService artifacts;

  public PublicArtifactController(ArtifactService artifacts) {
    this.artifacts = artifacts;
  }

  @GetMapping("/artifacts/{runId}/{*path}")
  public ResponseEntity<Resource> get(
      @PathVariable String runId,
      @PathVariable("path") String path) {
    String cleaned = path.startsWith("/") ? path.substring(1) : path;
    return artifacts.getPublic(runId, cleaned);
  }
}
