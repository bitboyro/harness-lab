package ro.bitboy.harness.ui.core;

import java.nio.file.Path;

/** Artifact path resolution with traversal rejection (contracts.md). */
public final class PathsSafe {

  private PathsSafe() {}

  /**
   * Resolve {@code name} under {@code artifactsRoot}. Rejects escapes with
   * {@link CliException} exit 2 → HTTP 400.
   */
  public static Path resolveUnder(Path artifactsRoot, String name) {
    if (name == null || name.isBlank()) {
      throw new CliException(2, 400, "artifact name required");
    }
    if (name.contains("\0")) {
      throw new CliException(2, 400, "invalid artifact name");
    }
    // Reject any `..` (decoded segments or still-percent-encoded forms).
    if (name.contains("..") || name.toLowerCase().contains("%2e%2e")) {
      throw new CliException(2, 400, "path traversal rejected");
    }
    Path relative = Path.of(name);
    Path root = artifactsRoot.toAbsolutePath().normalize();
    Path resolved = root.resolve(relative).normalize();
    if (!resolved.startsWith(root)) {
      throw new CliException(2, 400, "path traversal rejected");
    }
    return resolved;
  }
}
