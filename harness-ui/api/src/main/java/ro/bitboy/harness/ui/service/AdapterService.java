package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.core.ExitCodeMapper;
import ro.bitboy.harness.ui.core.HarnessCli;
import ro.bitboy.harness.ui.core.ProcessResult;

/**
 * Calls {@code harness_json.py}. Pack validation errors surface the Python
 * PackError text from stderr/JSON — never a Java-authored rewrite.
 */
@Service
public class AdapterService {

  private final HarnessCli cli;
  private final ObjectMapper mapper;

  public AdapterService(HarnessCli cli, ObjectMapper mapper) {
    this.cli = cli;
    this.mapper = mapper;
  }

  public JsonNode lint(String specPath) {
    return invokeJson("lint", List.of(specPath));
  }

  public JsonNode progress(String resultsDir) {
    return invokeJson("progress", List.of(resultsDir));
  }

  public JsonNode report(String resultsDir) {
    return invokeJson("report", List.of(resultsDir));
  }

  public JsonNode analyze(String resultsDir, String only) {
    List<String> args = new ArrayList<>();
    args.add(resultsDir);
    if (only != null && !only.isBlank()) {
      args.add("--only");
      args.add(only);
    }
    return invokeJson("analyze", args);
  }

  public JsonNode packValidate(String packPath, String baseUrl) {
    List<String> args = new ArrayList<>();
    args.add(packPath);
    if (baseUrl != null && !baseUrl.isBlank()) {
      args.add("--base-url");
      args.add(baseUrl);
    }
    ProcessResult result = cli.runAdapter("pack-validate", args);
    if (result.exitCode() == 0) {
      return parseJson(result.stdout());
    }
    // Prefer structured JSON error field if present; else raw stderr (PackError).
    if (result.stdout() != null && result.stdout().trim().startsWith("{")) {
      try {
        JsonNode node = mapper.readTree(result.stdout());
        if (node.has("error") && !node.get("error").isNull()) {
          // Still return the adapter JSON on soft-invalid packs (valid:false).
          return node;
        }
      } catch (Exception ignored) {
        // fall through
      }
    }
    String packError = packErrorText(result);
    throw new CliException(result.exitCode(), packError);
  }

  public JsonNode invokeJson(String subcommand, List<String> args) {
    ProcessResult result = cli.runAdapter(subcommand, args);
    if (result.exitCode() != 0) {
      throw new CliException(
          result.exitCode(),
          ExitCodeMapper.clientMessage(result.exitCode(), result.stderr()));
    }
    return parseJson(result.stdout());
  }

  public JsonNode invokeJsonArgs(List<String> adapterArgs) {
    ProcessResult result = cli.runAdapterArgs(adapterArgs);
    if (result.exitCode() != 0) {
      throw new CliException(
          result.exitCode(),
          ExitCodeMapper.clientMessage(result.exitCode(), result.stderr()));
    }
    return parseJson(result.stdout());
  }

  public JsonNode runConfig() {
    return invokeJson("run-config", List.of());
  }

  public JsonNode experimentRead(String resultsDir, String slice) {
    List<String> args = new ArrayList<>();
    args.add("experiment");
    args.add("read");
    args.add(resultsDir);
    if (slice != null && !slice.isBlank()) {
      args.add("--slice");
      args.add(slice);
    }
    return invokeJsonArgs(args);
  }

  public JsonNode experimentCoverage(String resultsDir, String slice) {
    List<String> args = new ArrayList<>();
    args.add("experiment");
    args.add("coverage");
    args.add(resultsDir);
    if (slice != null && !slice.isBlank()) {
      args.add("--slice");
      args.add(slice);
    }
    return invokeJsonArgs(args);
  }

  public JsonNode experimentMissing(String resultsDir, String slice) {
    List<String> args = new ArrayList<>();
    args.add("experiment");
    args.add("missing");
    args.add(resultsDir);
    if (slice != null && !slice.isBlank()) {
      args.add("--slice");
      args.add(slice);
    }
    return invokeJsonArgs(args);
  }

  public JsonNode experimentSnapshot(String resultsDir) {
    return invokeJsonArgs(List.of("experiment", "snapshot", resultsDir));
  }

  public JsonNode generateStatus(String workspaceDir) {
    return invokeJson("generate-status", List.of(workspaceDir));
  }

  public JsonNode generateManifest(String workspaceDir) {
    return invokeJson("generate-manifest", List.of(workspaceDir));
  }

  private JsonNode parseJson(String stdout) {
    try {
      return mapper.readTree(stdout == null || stdout.isBlank() ? "{}" : stdout);
    } catch (Exception e) {
      throw new CliException(40, "adapter returned non-JSON");
    }
  }

  /** Surface Python PackError text verbatim when possible. */
  static String packErrorText(ProcessResult result) {
    if (result.stderr() != null && !result.stderr().isBlank()) {
      return result.stderr().lines()
          .map(String::trim)
          .filter(s -> !s.isEmpty())
          .filter(s -> !s.startsWith("loaded from"))
          .findFirst()
          .orElse(result.stderr().trim());
    }
    if (result.stdout() != null && !result.stdout().isBlank()) {
      return result.stdout().trim();
    }
    return "pack validation failed";
  }
}
