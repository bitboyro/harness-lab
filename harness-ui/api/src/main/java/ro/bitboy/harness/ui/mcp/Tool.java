package ro.bitboy.harness.ui.mcp;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Marks a method as an MCP tool. {@link #name()} must match a {@code Capabilities} constant
 * and the REST {@code operationId} — frozen in {@code harness-ui/docs/contracts.md}.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Tool {
  /** MCP tool name and REST operationId. */
  String name();

  String description();
}
