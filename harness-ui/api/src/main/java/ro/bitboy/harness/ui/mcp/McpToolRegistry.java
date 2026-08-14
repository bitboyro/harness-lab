package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Component
public class McpToolRegistry {

  private static final JsonNode OPEN_ARGS =
      new ObjectMapper().createObjectNode().put("type", "object");

  private final Map<String, McpToolDefinition> tools;

  public McpToolRegistry(
      TargetTools targetTools,
      PackTools packTools,
      RunTools runTools,
      CompareTools compareTools,
      ExperimentTools experimentTools,
      GenerateTools generateTools,
      ConfigTools configTools) {
    this.tools = Collections.unmodifiableMap(register(
        targetTools, packTools, runTools, compareTools, experimentTools, generateTools,
        configTools));
  }

  private static Map<String, McpToolDefinition> register(Object... beans) {
    Map<String, McpToolDefinition> built = new LinkedHashMap<>();
    for (Object bean : beans) {
      Class<?> type = AopUtils.getTargetClass(bean);
      for (Method method : type.getDeclaredMethods()) {
        Tool ann = method.getAnnotation(Tool.class);
        if (ann == null) {
          continue;
        }
        if (built.containsKey(ann.name())) {
          throw new IllegalStateException("duplicate MCP tool: " + ann.name());
        }
        method.setAccessible(true);
        built.put(
            ann.name(),
            new McpToolDefinition(ann.name(), ann.description(), OPEN_ARGS, bean, method));
      }
    }
    return built;
  }

  public List<McpToolDefinition> list() {
    return new ArrayList<>(tools.values());
  }

  public Optional<McpToolDefinition> get(String name) {
    return Optional.ofNullable(tools.get(name));
  }

  public Map<String, McpToolDefinition> byName() {
    return tools;
  }
}
