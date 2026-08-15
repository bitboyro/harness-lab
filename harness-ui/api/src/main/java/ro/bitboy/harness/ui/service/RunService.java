package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.core.DiskDelete;
import ro.bitboy.harness.ui.core.ExitCodeMapper;
import ro.bitboy.harness.ui.core.HarnessCli;
import ro.bitboy.harness.ui.core.JobRegistry;
import ro.bitboy.harness.ui.core.Jsonl;
import ro.bitboy.harness.ui.core.ProcessResult;
import ro.bitboy.harness.ui.dto.CellRef;
import ro.bitboy.harness.ui.dto.CostProjection;
import ro.bitboy.harness.ui.dto.ProgressEnvelope;
import ro.bitboy.harness.ui.dto.RunJob;
import ro.bitboy.harness.ui.dto.RunRequest;
import ro.bitboy.harness.ui.dto.RunSummary;
import ro.bitboy.harness.ui.dto.TranscriptResponse;

@Service
public class RunService {

  private final HarnessProperties props;
  private final HarnessCli cli;
  private final JobRegistry jobs;
  private final PackService packs;
  private final TargetService targets;
  private final AdapterService adapter;
  private final ObjectMapper mapper;
  private final ProviderCatalogService providers;

  public RunService(
      HarnessProperties props,
      HarnessCli cli,
      JobRegistry jobs,
      PackService packs,
      TargetService targets,
      AdapterService adapter,
      ObjectMapper mapper,
      ProviderCatalogService providers) {
    this.props = props;
    this.cli = cli;
    this.jobs = jobs;
    this.packs = packs;
    this.targets = targets;
    this.adapter = adapter;
    this.mapper = mapper;
    this.providers = providers;
  }

  public CostProjection project(RunRequest req) {
    validateSandbox(req);
    List<String> args = buildRunArgs(req, false);
    ProcessResult result = cli.runHarness(args, providers.envFor(req.provider(), req.model()));
    // Exit 1 is the expected dry-run / confirm-gate success for projection.
    if (result.exitCode() != ExitCodeMapper.DECLINED && result.exitCode() != ExitCodeMapper.SUCCESS) {
      throw new CliException(
          result.exitCode(),
          ExitCodeMapper.clientMessage(result.exitCode(), result.stderr()));
    }
    return new CostProjection(
        result.stdout() == null ? "" : result.stdout(),
        result.exitCode() == 0 ? 1 : result.exitCode(),
        HarnessCli.extractStderrNames(result.stderr()));
  }

  public RunJob start(RunRequest req) {
    if (req.approve() == null || !req.approve()) {
      throw new CliException(2, 400, "approve must be true to start a run");
    }
    validateSandbox(req);
    Path outDir = props.resultsDir().resolve(req.id());
    try {
      Files.createDirectories(outDir);
    } catch (IOException e) {
      throw new CliException(40, "cannot create results dir: " + e.getMessage());
    }
    RunJob job = jobs.createQueued(req.id(), outDir);
    List<String> args = buildRunArgs(req, !req.dryRun());
    Path console = jobs.consoleLog(req.id());
    Process process = cli.startHarness(args, console, providers.envFor(req.provider(), req.model()));
    job = jobs.markRunning(req.id(), process);
    Process finalProcess = process;
    String id = req.id();
    Thread waiter = new Thread(() -> {
      try {
        int code = finalProcess.waitFor();
        jobs.markTerminal(id, code, null, jobs.messageForExit(id, code));
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        jobs.markTerminal(id, ExitCodeMapper.CANCELLED, "cancelled", "interrupted");
      }
    }, "job-wait-" + id);
    waiter.setDaemon(true);
    waiter.start();
    return job;
  }

  public ProgressEnvelope progress(String id) {
    Path out = props.resultsDir().resolve(id);
    var existing = jobs.find(id);
    if (existing.isEmpty()) {
      // Fixture / prior CLI run: results on disk, no owned process.
      if (!Files.isDirectory(out)) {
        throw new CliException(2, 404, "unknown run: " + id);
      }
      long rows = Jsonl.countRows(out.resolve("results.jsonl"));
      RunJob synthetic = new RunJob(
          id,
          rows > 0 ? RunJob.Status.succeeded : RunJob.Status.failed,
          null,
          null,
          out.toString(),
          null,
          null,
          null,
          "results on disk; no owned job process");
      return new ProgressEnvelope(synthetic, progressJson(out), true);
    }

    // Reap exited process into terminal status before answering.
    boolean alive = jobs.isAlive(id);
    RunJob job = jobs.require(id);
    boolean terminal = job.status().isTerminal()
        || (!alive && job.status() != RunJob.Status.queued);
    out = Path.of(job.outDir());
    return new ProgressEnvelope(job, progressJson(out), terminal);
  }

  private JsonNode progressJson(Path out) {
    try {
      return adapter.progress(out.toString());
    } catch (CliException e) {
      // Empty / torn ledger mid-run: return a minimal progress object.
      ObjectNode n = mapper.createObjectNode();
      n.put("harness_version", props.getExpectVersion());
      n.put("done", (int) Jsonl.countRows(out.resolve("results.jsonl")));
      n.putNull("expected");
      n.put("elapsed_seconds", 0);
      n.putObject("by_arm");
      n.putObject("outcomes");
      n.put("note", e.getMessage());
      return n;
    }
  }

  public List<RunSummary> list() {
    Set<String> ids = new HashSet<>();
    Path results = props.resultsDir();
    if (Files.isDirectory(results)) {
      try (var stream = Files.list(results)) {
        stream.filter(Files::isDirectory).forEach(p -> ids.add(p.getFileName().toString()));
      } catch (IOException e) {
        throw new CliException(40, "cannot list results: " + e.getMessage());
      }
    }
    Path jobsDir = props.jobsDir();
    if (Files.isDirectory(jobsDir)) {
      try (var stream = Files.list(jobsDir)) {
        stream.filter(Files::isDirectory).forEach(p -> ids.add(p.getFileName().toString()));
      } catch (IOException e) {
        throw new CliException(40, "cannot list jobs: " + e.getMessage());
      }
    }
    List<RunSummary> out = new ArrayList<>();
    for (String id : ids) {
      RunJob job = jobs.find(id).orElse(null);
      Path outDir = job != null ? Path.of(job.outDir()) : props.resultsDir().resolve(id);
      long rows = Jsonl.countRows(outDir.resolve("results.jsonl"));
      out.add(new RunSummary(
          id,
          job != null ? job.status().name() : (rows > 0 ? "succeeded" : "unknown"),
          outDir.toString(),
          job != null ? job.startedAt() : null,
          job != null ? job.finishedAt() : null,
          rows));
    }
    out.sort(Comparator.comparing(RunSummary::startedAt, Comparator.nullsLast(Comparator.naturalOrder())).reversed());
    return out;
  }

  public JsonNode report(String id) {
    Path out = resultsDir(id);
    return adapter.report(out.toString());
  }

  public JsonNode analysis(String id, String only) {
    Path out = resultsDir(id);
    return adapter.analyze(out.toString(), only);
  }

  public JsonNode brief(String id) {
    // Same serializer as report (contracts.md) until a dedicated brief lands.
    return report(id);
  }

  public TranscriptResponse transcript(String id, String arm, String taskId, int repeat,
      boolean verbose) {
    Path out = resultsDir(id);
    String runId = findRunId(out.resolve("results.jsonl"), arm, taskId, repeat);
    Path trace = out.resolve("traces").resolve(runId + ".json.gz");
    if (!Files.isRegularFile(trace)) {
      Path plain = out.resolve("traces").resolve(runId + ".json");
      if (Files.isRegularFile(plain)) {
        trace = plain;
      } else {
        throw new CliException(2, 404, "trace not found for " + arm + "/" + taskId + "/" + repeat);
      }
    }
    List<String> args = new ArrayList<>(List.of("transcript", trace.toString(), "--pretty"));
    if (verbose) {
      args.add("--verbose");
    }
    ProcessResult result = cli.runHarness(args);
    if (result.exitCode() != 0) {
      throw new CliException(
          result.exitCode(),
          ExitCodeMapper.clientMessage(result.exitCode(), result.stderr()));
    }
    return new TranscriptResponse(result.stdout() == null ? "" : result.stdout());
  }

  /** Latest row per (arm, task, repeat) for transcript picker. */
  public List<CellRef> listCells(String id) {
    Path ledger = resultsDir(id).resolve("results.jsonl");
    if (!Files.isRegularFile(ledger)) {
      return List.of();
    }
    Map<String, CellRef> latest = new LinkedHashMap<>();
    for (String line : Jsonl.readLinesTolerant(ledger)) {
      try {
        JsonNode n = mapper.readTree(line);
        String arm = n.path("arm").asText("");
        String taskId = n.path("task_id").asText("");
        if (arm.isBlank() || taskId.isBlank()) {
          continue;
        }
        int repeat = n.path("repeat").asInt(0);
        String key = arm + "\0" + taskId + "\0" + repeat;
        latest.put(
            key,
            new CellRef(
                arm,
                taskId,
                repeat,
                n.path("outcome").asText(null),
                n.path("turns").asInt(0),
                n.path("calls").asInt(0)));
      } catch (Exception ignored) {
        // skip corrupt line
      }
    }
    List<CellRef> out = new ArrayList<>(latest.values());
    out.sort(
        Comparator.comparing(CellRef::arm)
            .thenComparing(CellRef::taskId)
            .thenComparingInt(CellRef::repeat));
    return out;
  }

  public Path resultsDir(String id) {
    Path out = props.resultsDir().resolve(id);
    if (!Files.isDirectory(out) && jobs.find(id).isEmpty()) {
      throw new CliException(2, 404, "unknown run: " + id);
    }
    return out;
  }

  private void validateSandbox(RunRequest req) {
    if (req.allowCodeSandbox()) {
      return;
    }
    for (String p : req.presets()) {
      String upper = p.toUpperCase(Locale.ROOT);
      if (upper.equals("D1") || upper.equals("D2") || upper.startsWith("D1") || upper.startsWith("D2")) {
        throw new CliException(2, 400, "presets D1/D2 require allowCodeSandbox=true");
      }
    }
  }

  private List<String> buildRunArgs(RunRequest req, boolean approveAndStream) {
    List<String> args = new ArrayList<>();
    args.add("run");
    args.add("--id");
    args.add(req.id());
    args.add("--out");
    args.add(props.resultsDir().resolve(req.id()).toString());
    if (req.presets() != null && !req.presets().isEmpty()) {
      args.add("--presets");
      args.addAll(req.presets());
    }
    if (req.model() != null && !req.model().isBlank()) {
      args.add("--model");
      args.add(req.model());
    }
    if (req.provider() != null && !req.provider().isBlank()) {
      args.add("--provider");
      args.add(providers.adapterName(req.provider()));
    }
    if (req.reasoningEffort() != null && !req.reasoningEffort().isBlank()) {
      args.add("--reasoning-effort");
      args.add(req.reasoningEffort());
    }
    args.add("--repeats");
    args.add(String.valueOf(req.repeats()));
    if (req.smoke()) {
      args.add("--smoke");
    }
    if (req.probe()) {
      args.add("--probe");
    }
    if (req.resume()) {
      args.add("--resume");
    }
    if (req.packId() != null && !req.packId().isBlank()) {
      args.add("--pack");
      args.add(packs.requirePackFile(req.packId()).toString());
    }
    if (req.targetId() != null && !req.targetId().isBlank()) {
      var t = targets.require(req.targetId());
      if ("openapi".equals(t.kind())) {
        args.add("--spec");
        args.add(targets.specOrUrlPath(req.targetId()).toString());
      }
    }
    if (approveAndStream) {
      args.add("--yes");
      args.add("--stream");
    }
    appendDiskReserve(args);
    return args;
  }

  private void appendDiskReserve(List<String> args) {
    if (props.getDiskReserveGb() != null) {
      args.add("--disk-reserve-gb");
      args.add(String.valueOf(props.getDiskReserveGb()));
    }
  }

  private String findRunId(Path ledger, String arm, String taskId, int repeat) {
    String found = null;
    for (String line : Jsonl.readLinesTolerant(ledger)) {
      try {
        JsonNode n = mapper.readTree(line);
        if (arm.equals(n.path("arm").asText())
            && taskId.equals(n.path("task_id").asText())
            && repeat == n.path("repeat").asInt()) {
          found = n.path("run_id").asText(null);
        }
      } catch (Exception ignored) {
        // torn / corrupt line already filtered mostly
      }
    }
    if (found == null || found.isBlank()) {
      throw new CliException(2, 404, "no ledger row for " + arm + "/" + taskId + "/" + repeat);
    }
    return found;
  }

  public void delete(String id) {
    validateId(id);
    Path results = props.resultsDir().resolve(id);
    Path jobDir = props.jobsDir().resolve(id);
    if (!Files.isDirectory(results) && !Files.isDirectory(jobDir)) {
      throw new CliException(2, 404, "unknown run: " + id);
    }
    jobs.cancelForDelete(id);
    DiskDelete.deleteTree(results);
    DiskDelete.deleteTree(jobDir);
  }

  private static void validateId(String id) {
    if (id == null || id.isBlank() || id.contains("..") || id.contains("/") || id.contains("\\")) {
      throw new CliException(2, 400, "invalid run id");
    }
  }
}
