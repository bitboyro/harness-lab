package ro.bitboy.harness.ui.core;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

/** Recursive delete for workspace artifacts (runs, targets, …). */
public final class DiskDelete {

  private DiskDelete() {}

  public static void deleteTree(Path root) {
    if (!Files.exists(root)) {
      return;
    }
    try (Stream<Path> walk = Files.walk(root)) {
      walk.sorted(Comparator.reverseOrder()).forEach(p -> {
        try {
          Files.deleteIfExists(p);
        } catch (IOException e) {
          throw new CliException(40, "cannot delete " + p + ": " + e.getMessage());
        }
      });
    } catch (IOException e) {
      throw new CliException(40, "cannot delete " + root + ": " + e.getMessage());
    }
  }
}
