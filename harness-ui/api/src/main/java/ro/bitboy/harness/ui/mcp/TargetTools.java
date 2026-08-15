package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.dto.Target;
import ro.bitboy.harness.ui.dto.TargetContract;
import ro.bitboy.harness.ui.service.AdapterService;
import ro.bitboy.harness.ui.service.TargetService;

@Component
public class TargetTools {

  private final TargetService targets;
  private final AdapterService adapter;

  public TargetTools(TargetService targets, AdapterService adapter) {
    this.targets = targets;
    this.adapter = adapter;
  }

  @Tool(name = Capabilities.UPLOAD_CONTRACT, description = "Upload an OpenAPI contract file or register an MCP server URL.")
  public Target uploadContract(JsonNode args) {
    if (args != null && args.hasNonNull("mcp_url")) {
      return targets.upload(null, args.get("mcp_url").asText());
    }
    if (args != null && args.hasNonNull("file_base64")) {
      byte[] bytes = Base64.getDecoder().decode(args.get("file_base64").asText());
      String filename = args.path("filename").asText("spec.json");
      MultipartFile file =
          new BytesMultipartFile("file", filename, "application/octet-stream", bytes);
      return targets.upload(file, null);
    }
    throw new CliException(2, 400, "provide mcp_url or file_base64");
  }

  @Tool(name = Capabilities.LIST_TARGETS, description = "List uploaded API targets.")
  public java.util.List<Target> listTargets() {
    return targets.list();
  }

  @Tool(name = Capabilities.GET_TARGET, description = "Get one target by id.")
  public Target getTarget(String id) {
    return targets.require(id);
  }

  @Tool(name = Capabilities.READ_TARGET_CONTRACT, description = "Read OpenAPI text or MCP URL for a target.")
  public TargetContract readTargetContract(String id) {
    return targets.readContract(id);
  }

  @Tool(name = Capabilities.WRITE_TARGET_CONTRACT, description = "Write OpenAPI text or MCP URL for a target.")
  public void writeTargetContract(String id, String text) {
    targets.writeContract(id, text);
  }

  @Tool(name = Capabilities.LINT_TARGET, description = "Run harness lint on an OpenAPI target.")
  public JsonNode lintTarget(String id) {
    Target t = targets.require(id);
    if ("mcp".equals(t.kind())) {
      throw new CliException(2, 400, "lint requires an OpenAPI target");
    }
    return adapter.lint(targets.specOrUrlPath(id).toString());
  }

  @Tool(name = Capabilities.DELETE_TARGET, description = "Delete a target directory.")
  public void deleteTarget(String id) {
    targets.delete(id);
  }
}
