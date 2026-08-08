package ro.bitboy.harness.ui.web;

import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.Target;
import ro.bitboy.harness.ui.service.AdapterService;
import ro.bitboy.harness.ui.service.TargetService;

@RestController
@RequestMapping("/api/v1/targets")
public class TargetController {

  private final TargetService targets;
  private final AdapterService adapter;

  public TargetController(TargetService targets, AdapterService adapter) {
    this.targets = targets;
    this.adapter = adapter;
  }

  @PostMapping(consumes = {"multipart/form-data"})
  @ResponseStatus(HttpStatus.CREATED)
  @Operation(operationId = Capabilities.UPLOAD_CONTRACT)
  public Target upload(
      @RequestParam(value = "file", required = false) MultipartFile file,
      @RequestParam(value = "mcp_url", required = false) String mcpUrl) {
    return targets.upload(file, mcpUrl);
  }

  @GetMapping
  @Operation(operationId = Capabilities.LIST_TARGETS)
  public List<Target> list() {
    return targets.list();
  }

  @PostMapping("/{id}/lint")
  @Operation(operationId = Capabilities.LINT_TARGET)
  public JsonNode lint(@PathVariable String id) {
    Target t = targets.require(id);
    if ("mcp".equals(t.kind())) {
      throw new ro.bitboy.harness.ui.core.CliException(2, 400, "lint requires an OpenAPI target");
    }
    return adapter.lint(targets.specOrUrlPath(id).toString());
  }
}
