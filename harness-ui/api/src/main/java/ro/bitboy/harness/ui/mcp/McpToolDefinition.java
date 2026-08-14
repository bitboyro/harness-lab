package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import java.lang.reflect.Method;

record McpToolDefinition(
    String name,
    String description,
    JsonNode inputSchema,
    Object bean,
    Method method
) {}
