package ro.bitboy.harness.ui.web;

import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import java.util.List;
import jakarta.validation.Valid;
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
import org.springframework.web.multipart.MultipartFile;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.Target;
import ro.bitboy.harness.ui.dto.TargetContract;
import ro.bitboy.harness.ui.dto.WriteTargetContractRequest;
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

  @GetMapping("/{id}")
  @Operation(operationId = Capabilities.GET_TARGET)
  public Target get(@PathVariable String id) {
    return targets.require(id);
  }

  @GetMapping("/{id}/contract")
  @Operation(operationId = Capabilities.READ_TARGET_CONTRACT)
  public TargetContract readContract(@PathVariable String id) {
    return targets.readContract(id);
  }

  @PutMapping("/{id}/contract")
  @Operation(operationId = Capabilities.WRITE_TARGET_CONTRACT)
  public void writeContract(
      @PathVariable String id, @Valid @RequestBody WriteTargetContractRequest body) {
    targets.writeContract(id, body.text());
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

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  @Operation(operationId = Capabilities.DELETE_TARGET)
  public void delete(@PathVariable String id) {
    targets.delete(id);
  }
}
