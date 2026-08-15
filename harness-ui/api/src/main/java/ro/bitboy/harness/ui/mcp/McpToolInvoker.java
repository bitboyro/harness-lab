package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.core.CliException;

@Component
public class McpToolInvoker {

  private final ObjectMapper mapper;

  public McpToolInvoker(ObjectMapper mapper) {
    this.mapper = mapper;
  }

  public Object invoke(McpToolDefinition def, JsonNode arguments) {
    try {
      Method method = def.method();
      Parameter[] params = method.getParameters();
      if (params.length == 0) {
        return method.invoke(def.bean());
      }
      if (params.length == 1 && params[0].getType().isAssignableFrom(JsonNode.class)) {
        JsonNode args = arguments == null ? mapper.nullNode() : arguments;
        return method.invoke(def.bean(), args);
      }
      Object[] args = new Object[params.length];
      for (int i = 0; i < params.length; i++) {
        String name = params[i].getName();
        JsonNode node = arguments == null ? null : arguments.get(name);
        if (node == null || node.isNull()) {
          args[i] = null;
        } else {
          args[i] = mapper.convertValue(node, params[i].getType());
        }
      }
      return method.invoke(def.bean(), args);
    } catch (CliException e) {
      throw e;
    } catch (Exception e) {
      Throwable cause = e.getCause() != null ? e.getCause() : e;
      if (cause instanceof CliException cli) {
        throw cli;
      }
      throw new CliException(40, "tool invocation failed: " + cause.getMessage());
    }
  }
}
