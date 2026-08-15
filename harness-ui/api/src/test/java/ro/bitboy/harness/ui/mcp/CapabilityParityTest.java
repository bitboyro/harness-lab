package ro.bitboy.harness.ui.mcp;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import ro.bitboy.harness.ui.Capabilities;

/**
 * T5.2 — build fails if any {@link Capabilities} constant lacks an MCP tool (or vice versa).
 */
@SpringBootTest
class CapabilityParityTest {

  @DynamicPropertySource
  static void props(DynamicPropertyRegistry registry) {
    registry.add("harness.data", () -> System.getProperty("java.io.tmpdir"));
    registry.add("harness.cli", () -> "harness");
    registry.add("harness.adapter", () -> "python3");
    registry.add("harness.adapter-script", () -> "/tmp/missing-adapter.py");
    registry.add("server.port", () -> "0");
  }

  @Autowired
  McpToolRegistry registry;

  @Test
  void everyCapabilityHasMatchingMcpTool() throws Exception {
    Set<String> caps = capabilityNames();
    Set<String> tools = registry.byName().keySet();
    assertEquals(caps, tools, () -> missingMessage(caps, tools));
  }

  private static Set<String> capabilityNames() throws Exception {
    Set<String> names = new java.util.TreeSet<>();
    for (Field f : Capabilities.class.getDeclaredFields()) {
      if (Modifier.isStatic(f.getModifiers())
          && Modifier.isFinal(f.getModifiers())
          && f.getType() == String.class) {
        names.add((String) f.get(null));
      }
    }
    return names;
  }

  private static String missingMessage(Set<String> caps, Set<String> tools) {
    Set<String> missingTools = caps.stream().filter(c -> !tools.contains(c)).collect(Collectors.toSet());
    Set<String> extraTools = tools.stream().filter(t -> !caps.contains(t)).collect(Collectors.toSet());
    StringBuilder sb = new StringBuilder("capability / MCP tool mismatch\n");
    if (!missingTools.isEmpty()) {
      sb.append("  missing tools: ").append(missingTools).append('\n');
    }
    if (!extraTools.isEmpty()) {
      sb.append("  extra tools: ").append(extraTools).append('\n');
    }
    return sb.toString();
  }

  @Test
  void registryIsNonEmpty() {
    assertTrue(registry.list().size() >= 25);
  }
}
