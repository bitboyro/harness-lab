package ro.bitboy.harness.ui.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.core.ExitCodeMapper;
import ro.bitboy.harness.ui.core.HarnessCli;
import ro.bitboy.harness.ui.core.ProcessResult;
import ro.bitboy.harness.ui.dto.CompareRequest;
import ro.bitboy.harness.ui.dto.CompareResult;

@Service
public class CompareService {

  private static final Pattern BOUNDARY_LINE = Pattern.compile(
      "^\\s*([A-Za-z0-9_.-]+)(?:\\s*\\(arm[^)]*\\))?:\\s+.+$");

  private final HarnessProperties props;
  private final HarnessCli cli;
  private final RunService runs;

  public CompareService(HarnessProperties props, HarnessCli cli, RunService runs) {
    this.props = props;
    this.cli = cli;
    this.runs = runs;
  }

  public CompareResult compare(CompareRequest req) {
    if (req.runIds() == null || req.runIds().size() < 2) {
      throw new CliException(2, 400, "compare needs at least two runIds");
    }
    String compareId = "cmp-" + UUID.randomUUID().toString().replace("-", "").substring(0, 10);
    Path artifactDir = props.compareDir().resolve(compareId).resolve("artifacts");
    try {
      Files.createDirectories(artifactDir);
    } catch (IOException e) {
      throw new CliException(40, "cannot create compare dir: " + e.getMessage());
    }
    List<String> args = new ArrayList<>();
    args.add("compare");
    for (String id : req.runIds()) {
      args.add(runs.resultsDir(id).toString());
    }
    args.add("--html");
    args.add(artifactDir.resolve("compare.html").toString());
    args.add("--charts");
    args.add(artifactDir.resolve("charts").toString());
    ProcessResult result = cli.runHarness(args);
    String stdout = result.stdout() == null ? "" : result.stdout();
    String combined = result.combinedOutput();

    if (result.exitCode() == ExitCodeMapper.POOLING_REFUSED) {
      // Never swallow exit 3 — surface refusal on HTTP 200.
      String refusal = extractRefusal(combined);
      return new CompareResult(
          true,
          refusal,
          extractBoundary(refusal),
          "compare/" + compareId + "/artifacts",
          stdout);
    }
    if (result.exitCode() != 0) {
      throw new CliException(
          result.exitCode(),
          ExitCodeMapper.clientMessage(result.exitCode(), result.stderr()));
    }
    return new CompareResult(
        false,
        null,
        null,
        "compare/" + compareId + "/artifacts",
        stdout);
  }

  static String extractRefusal(String text) {
    if (text == null) {
      return "REFUSING TO POOL";
    }
    int idx = text.indexOf("REFUSING TO POOL");
    if (idx < 0) {
      return text.trim().isEmpty() ? "REFUSING TO POOL" : text.trim();
    }
    return text.substring(idx).trim();
  }

  static String extractBoundary(String refusalText) {
    if (refusalText == null) {
      return null;
    }
    for (String line : refusalText.split("\\R")) {
      if (line.contains("REFUSING TO POOL")) {
        continue;
      }
      Matcher m = BOUNDARY_LINE.matcher(line);
      if (m.matches()) {
        return m.group(1);
      }
    }
    return null;
  }
}
