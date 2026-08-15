package ro.bitboy.harness.ui.core;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Ledger helpers. A torn last line (process killed mid-append) is skipped, not
 * fatal — same tolerance the adapter/progress path needs.
 */
public final class Jsonl {

  private Jsonl() {}

  public static long countRows(Path ledger) {
    return readLinesTolerant(ledger).size();
  }

  public static List<String> readLinesTolerant(Path ledger) {
    if (!Files.isRegularFile(ledger)) {
      return List.of();
    }
    List<String> lines = new ArrayList<>();
    try (BufferedReader r = Files.newBufferedReader(ledger, StandardCharsets.UTF_8)) {
      String line;
      while ((line = r.readLine()) != null) {
        String trimmed = line.trim();
        if (trimmed.isEmpty()) {
          continue;
        }
        // Skip a torn final line that is not valid JSON object text.
        if (!(trimmed.startsWith("{") && trimmed.endsWith("}"))) {
          continue;
        }
        lines.add(trimmed);
      }
    } catch (IOException e) {
      throw new CliException(40, "cannot read ledger: " + e.getMessage());
    }
    return lines;
  }
}
