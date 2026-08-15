package ro.bitboy.harness.ui.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class PathsSafeTest {

  @TempDir
  Path root;

  @Test
  void rejectsDotDotTraversal() {
    CliException ex = assertThrows(
        CliException.class,
        () -> PathsSafe.resolveUnder(root.resolve("artifacts"), "../../etc/passwd"));
    assertEquals(400, ex.getHttpStatus());
    assertEquals(2, ex.getExitCode());
    assertTrue(ex.getMessage().toLowerCase().contains("traversal"));
  }

  @Test
  void acceptsNestedSafeName() {
    Path resolved = PathsSafe.resolveUnder(root.resolve("artifacts"), "charts/score.svg");
    assertTrue(resolved.startsWith(root.resolve("artifacts").toAbsolutePath().normalize()));
  }
}
