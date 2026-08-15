package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import ro.bitboy.harness.ui.core.CliException;

/**
 * Minimal MCP JSON-RPC surface: {@code tools/list} and {@code tools/call}.
 * Capability names match REST {@code operationId}s — see {@code Capabilities}.
 */
@RestController
@RequestMapping("/mcp")
public class McpController {

  private final McpToolRegistry registry;
  private final McpToolInvoker invoker;
  private final ObjectMapper mapper;

  public McpController(McpToolRegistry registry, McpToolInvoker invoker, ObjectMapper mapper) {
    this.registry = registry;
    this.invoker = invoker;
    this.mapper = mapper;
  }

  @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
  public JsonNode handle(@RequestBody JsonNode body) {
    String method = body.path("method").asText("");
    JsonNode id = body.get("id");
    return switch (method) {
      case "initialize" -> ok(id, initializeResult(body.path("params")));
      case "tools/list" -> ok(id, listTools());
      case "tools/call" -> callTool(id, body.path("params"));
      default -> error(id, -32601, "method not found: " + method);
    };
  }

  private ObjectNode initializeResult(JsonNode params) {
    ObjectNode result = mapper.createObjectNode();
    result.put("protocolVersion", "2026-07-28");
    ObjectNode serverInfo = result.putObject("serverInfo");
    serverInfo.put("name", "harness-ui");
    serverInfo.put("version", "0.0.1-SNAPSHOT");
    result.putObject("capabilities").putObject("tools");
    return result;
  }

  private ObjectNode listTools() {
    ObjectNode result = mapper.createObjectNode();
    ArrayNode tools = result.putArray("tools");
    for (McpToolDefinition def : registry.list()) {
      ObjectNode tool = tools.addObject();
      tool.put("name", def.name());
      tool.put("description", def.description());
      tool.set("inputSchema", def.inputSchema());
    }
    return result;
  }

  private JsonNode callTool(JsonNode id, JsonNode params) {
    String name = params.path("name").asText("");
    if (name.isBlank()) {
      return error(id, -32602, "missing tool name");
    }
    McpToolDefinition def =
        registry.get(name).orElseThrow(() -> new CliException(2, 404, "unknown tool: " + name));
    try {
      Object value = invoker.invoke(def, params.get("arguments"));
      return ok(id, toolResult(value));
    } catch (CliException e) {
      return error(id, e.getHttpStatus(), e.getMessage());
    }
  }

  private ObjectNode toolResult(Object value) {
    ObjectNode result = mapper.createObjectNode();
    ArrayNode content = result.putArray("content");
    ObjectNode text = content.addObject();
    text.put("type", "text");
    try {
      text.put("text", value == null ? "null" : mapper.writeValueAsString(value));
    } catch (Exception e) {
      text.put("text", String.valueOf(value));
    }
    result.put("isError", false);
    return result;
  }

  private ObjectNode ok(JsonNode id, ObjectNode result) {
    ObjectNode out = mapper.createObjectNode();
    out.put("jsonrpc", "2.0");
    if (id != null && !id.isNull()) {
      out.set("id", id);
    }
    out.set("result", result);
    return out;
  }

  private ObjectNode error(JsonNode id, int code, String message) {
    ObjectNode out = mapper.createObjectNode();
    out.put("jsonrpc", "2.0");
    if (id != null && !id.isNull()) {
      out.set("id", id);
    }
    ObjectNode err = out.putObject("error");
    err.put("code", code);
    err.put("message", message);
    return out;
  }
}
