package ro.bitboy.harness.ui.service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;

/**
 * Staging secrets for generate/fixture subprocesses (G6.2).
 *
 * <p>Values live under {@code /data/secrets/} as dotenv files — never in pack
 * YAML, generate.config.yaml, or console.log.
 */
@Service
public class SecretsService {

  private final HarnessProperties props;

  public SecretsService(HarnessProperties props) {
    this.props = props;
  }

  public Path secretsDir() {
    return props.secretsDir();
  }

  /** Write {@code secrets/<jobId>.env}; empty map deletes a prior file. */
  public Path writeGenerateEnv(String jobId, Map<String, String> values) {
    try {
      Path dir = secretsDir();
      Files.createDirectories(dir);
      Path file = dir.resolve(safeJobId(jobId) + ".env");
      if (values == null || values.isEmpty()) {
        Files.deleteIfExists(file);
        return file;
      }
      StringBuilder sb = new StringBuilder();
      sb.append("# generate staging secrets — do not commit\n");
      for (Map.Entry<String, String> e : values.entrySet()) {
        if (e.getKey() == null || e.getKey().isBlank() || e.getValue() == null) {
          continue;
        }
        sb.append(e.getKey().trim()).append('=').append(e.getValue()).append('\n');
      }
      Files.writeString(file, sb.toString(), StandardCharsets.UTF_8);
      try {
        Set<PosixFilePermission> perms = EnumSet.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.OWNER_WRITE);
        Files.setPosixFilePermissions(file, perms);
      } catch (UnsupportedOperationException ignored) {
        // non-POSIX (e.g. some CI volumes)
      }
      return file;
    } catch (IOException e) {
      throw new CliException(40, "cannot write secrets: " + e.getMessage());
    }
  }

  /** Load {@code secrets/<jobId>.env} into a map (no logging of values). */
  public Map<String, String> loadGenerateEnv(String jobId) {
    Path file = secretsDir().resolve(safeJobId(jobId) + ".env");
    if (!Files.isRegularFile(file)) {
      return Map.of();
    }
    try {
      Map<String, String> out = new LinkedHashMap<>();
      for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
        String trimmed = line.trim();
        if (trimmed.isEmpty() || trimmed.startsWith("#")) {
          continue;
        }
        int eq = trimmed.indexOf('=');
        if (eq <= 0) {
          continue;
        }
        out.put(trimmed.substring(0, eq).trim(), trimmed.substring(eq + 1));
      }
      return Map.copyOf(out);
    } catch (IOException e) {
      throw new CliException(40, "cannot read secrets: " + e.getMessage());
    }
  }

  private static String safeJobId(String jobId) {
    if (jobId == null || jobId.isBlank()) {
      throw new CliException(2, 400, "jobId required for secrets");
    }
    if (jobId.contains("..") || jobId.contains("/") || jobId.contains("\\")) {
      throw new CliException(2, 400, "invalid jobId for secrets");
    }
    return jobId;
  }
}
