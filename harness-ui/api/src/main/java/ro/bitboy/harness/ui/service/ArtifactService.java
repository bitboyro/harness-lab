package ro.bitboy.harness.ui.service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.core.ExitCodeMapper;
import ro.bitboy.harness.ui.core.HarnessCli;
import ro.bitboy.harness.ui.core.Jsonl;
import ro.bitboy.harness.ui.core.PathsSafe;
import ro.bitboy.harness.ui.core.ProcessResult;
import ro.bitboy.harness.ui.dto.ArtifactRef;

@Service
public class ArtifactService {

  public static final String CSP =
      "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; "
          + "style-src 'unsafe-inline'; img-src data: blob:; "
          + "font-src data:; connect-src 'none'; frame-ancestors 'none'; base-uri 'none'";

  private final HarnessProperties props;
  private final HarnessCli cli;
  private final RunService runs;

  public ArtifactService(HarnessProperties props, HarnessCli cli, RunService runs) {
    this.props = props;
    this.cli = cli;
    this.runs = runs;
  }

  public Path artifactsDir(String runId) {
    return runs.resultsDir(runId).resolve("artifacts");
  }

  public List<ArtifactRef> list(String runId) {
    ensureRendered(runId);
    Path root = artifactsDir(runId);
    if (!Files.isDirectory(root)) {
      return List.of();
    }
    List<ArtifactRef> out = new ArrayList<>();
    try (Stream<Path> walk = Files.walk(root)) {
      walk.filter(Files::isRegularFile).forEach(p -> {
        Path rel = root.relativize(p);
        try {
          out.add(new ArtifactRef(
              rel.toString().replace('\\', '/'),
              "results/" + runId + "/artifacts/" + rel.toString().replace('\\', '/'),
              Files.size(p)));
        } catch (IOException ignored) {
          // skip
        }
      });
    } catch (IOException e) {
      throw new CliException(40, "cannot list artifacts: " + e.getMessage());
    }
    return out;
  }

  public ResponseEntity<Resource> get(String runId, String name) {
    ensureRendered(runId);
    Path file = PathsSafe.resolveUnder(artifactsDir(runId), name);
    if (!Files.isRegularFile(file)) {
      throw new CliException(2, 404, "artifact not found: " + name);
    }
    return serve(file);
  }

  public ArtifactRef put(String runId, String name, InputStream body) {
    Path file = PathsSafe.resolveUnder(artifactsDir(runId), name);
    try {
      Files.createDirectories(file.getParent());
      Files.copy(body, file, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
      return new ArtifactRef(
          name,
          "results/" + runId + "/artifacts/" + name,
          Files.size(file));
    } catch (IOException e) {
      throw new CliException(40, "cannot write artifact: " + e.getMessage());
    }
  }

  public ResponseEntity<Resource> getPublic(String runId, String residualPath) {
    return get(runId, residualPath);
  }

  static ResponseEntity<Resource> serve(Path file) {
    String filename = file.getFileName().toString().toLowerCase(Locale.ROOT);
    MediaType type = MediaType.APPLICATION_OCTET_STREAM;
    if (filename.endsWith(".html") || filename.endsWith(".htm")) {
      type = MediaType.TEXT_HTML;
    } else if (filename.endsWith(".svg")) {
      type = MediaType.parseMediaType("image/svg+xml");
    } else if (filename.endsWith(".csv")) {
      type = MediaType.parseMediaType("text/csv");
    } else if (filename.endsWith(".json")) {
      type = MediaType.APPLICATION_JSON;
    } else if (filename.endsWith(".md")) {
      type = MediaType.TEXT_PLAIN;
    }
    return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_TYPE, type.toString())
        .header("X-Content-Type-Options", "nosniff")
        .header("Content-Security-Policy", CSP)
        .body(new FileSystemResource(file));
  }

  /**
   * Render-on-demand via {@code harness report}, cached by ledger row count.
   */
  public void ensureRendered(String runId) {
    Path results = runs.resultsDir(runId);
    Path ledger = results.resolve("results.jsonl");
    long rows = Jsonl.countRows(ledger);
    Path artifacts = artifactsDir(runId);
    Path stamp = artifacts.resolve(".cache-rows");
    try {
      if (Files.isRegularFile(stamp)) {
        String prev = Files.readString(stamp).trim();
        if (prev.equals(Long.toString(rows)) && Files.isDirectory(artifacts)) {
          return;
        }
      }
      Files.createDirectories(artifacts);
      Path html = artifacts.resolve("report.html");
      Path charts = artifacts.resolve("charts");
      Path csvDir = artifacts.resolve("csv");
      Files.createDirectories(charts);
      Files.createDirectories(csvDir);
      // HTML + charts
      ProcessResult r1 = cli.runHarness(List.of(
          "report", results.toString(),
          "--html", html.toString(),
          "--charts", charts.toString()));
      if (r1.exitCode() != 0 && r1.exitCode() != ExitCodeMapper.DECLINED) {
        // Soft: leave whatever exists; listing may be empty.
      }
      // CSV to stdout → file
      ProcessResult r2 = cli.runHarness(List.of("report", results.toString(), "--csv"));
      if (r2.exitCode() == 0 && r2.stdout() != null) {
        Files.writeString(
            csvDir.resolve("rows.csv"),
            r2.stdout(),
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING);
      }
      Files.writeString(stamp, Long.toString(rows));
    } catch (IOException e) {
      throw new CliException(40, "cannot render artifacts: " + e.getMessage());
    }
  }
}
