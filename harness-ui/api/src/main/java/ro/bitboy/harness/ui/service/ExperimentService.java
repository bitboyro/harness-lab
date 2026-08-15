package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.core.DiskDelete;
import ro.bitboy.harness.ui.core.ExitCodeMapper;
import ro.bitboy.harness.ui.core.HarnessCli;
import ro.bitboy.harness.ui.core.JobRegistry;
import ro.bitboy.harness.ui.core.ProcessResult;
import ro.bitboy.harness.ui.dto.AddExperimentArmsRequest;
import ro.bitboy.harness.ui.dto.CreateExperimentRequest;
import ro.bitboy.harness.ui.dto.ExperimentRef;
import ro.bitboy.harness.ui.dto.ExperimentRunProjection;
import ro.bitboy.harness.ui.dto.ExperimentRunRequest;
import ro.bitboy.harness.ui.dto.ExperimentSummary;
import ro.bitboy.harness.ui.dto.ReportSnapshotRef;
import ro.bitboy.harness.ui.dto.RunJob;
import ro.bitboy.harness.ui.dto.UpdateExperimentRequest;

@Service
public class ExperimentService {

  private static final String SIDECAR = "experiment.yaml";

  private final HarnessProperties props;
  private final HarnessCli cli;
  private final JobRegistry jobs;
  private final AdapterService adapter;
  private final SecretsService secrets;
  private final ProviderCatalogService providers;

  public ExperimentService(
      HarnessProperties props,
      HarnessCli cli,
      JobRegistry jobs,
      AdapterService adapter,
      SecretsService secrets,
      ProviderCatalogService providers) {
    this.props = props;
    this.cli = cli;
    this.jobs = jobs;
    this.adapter = adapter;
    this.secrets = secrets;
    this.providers = providers;
  }

  public List<ExperimentSummary> list(boolean all) {
    Path results = props.resultsDir();
    if (!Files.isDirectory(results)) {
      return List.of();
    }
    List<ExperimentSummary> out = new ArrayList<>();
    try (var stream = Files.list(results)) {
      stream.filter(Files::isDirectory).forEach(dir -> {
        Path sidecar = dir.resolve(SIDECAR);
        if (!Files.isRegularFile(sidecar)) {
          return;
        }
        try {
          JsonNode read = adapter.experimentRead(dir.toString(), null);
          JsonNode exp = read.path("experiment");
          JsonNode cov = read.path("coverage");
          Double fraction = cov.path("complete_fraction").isNull()
              ? null
              : cov.path("complete_fraction").asDouble();
          String model = exp.path("run_plan").path("base").path("model").asText(null);
          Instant updated = parseInstant(exp.path("updated_at").asText(null));
          // API id is the results directory name — GET /experiments/{id} resolves
          // the same path. The sidecar's experiment.id is a plan label and may
          // collide across copies (test-exp, baseline-experiment-80-1, …).
          String dirId = dir.getFileName().toString();
          String planId = exp.path("id").asText(null);
          if (planId != null && planId.equals(dirId)) {
            planId = null;
          }
          out.add(new ExperimentSummary(
              dirId,
              exp.path("status").asText("draft"),
              read.path("ledger").path("row_count").asInt(0) > 0,
              fraction,
              model,
              updated,
              planId));
        } catch (CliException ignored) {
          // skip unreadable sidecars
        }
      });
    } catch (IOException e) {
      throw new CliException(40, "cannot list experiments: " + e.getMessage());
    }
    out.sort(Comparator.comparing(ExperimentSummary::updatedAt,
        Comparator.nullsLast(Comparator.naturalOrder())).reversed());
    return out;
  }

  public ExperimentRef create(CreateExperimentRequest req) {
    Path out = props.resultsDir().resolve(req.id());
    try {
      Files.createDirectories(out);
    } catch (IOException e) {
      throw new CliException(40, "cannot create results dir: " + e.getMessage());
    }
    if (req.yaml() != null && !req.yaml().isBlank()) {
      if (req.planPath() != null && !req.planPath().isBlank()) {
        throw new CliException(2, 400, "set yaml or planPath, not both");
      }
      Path sidecar = out.resolve(SIDECAR);
      try {
        Files.writeString(sidecar, req.yaml());
      } catch (IOException e) {
        throw new CliException(40, "cannot write sidecar: " + e.getMessage());
      }
      validateSidecar(out);
      return new ExperimentRef(req.id(), sidecar.toString(), "draft", null);
    }
    if (req.planPath() == null || req.planPath().isBlank()) {
      throw new CliException(2, 400, "yaml or planPath required");
    }
    ProcessResult result = cli.runHarness(List.of(
        "experiment", "init", req.planPath(), "--out", out.toString()));
    if (result.exitCode() != 0) {
      throw new CliException(
          result.exitCode(),
          ExitCodeMapper.clientMessage(result.exitCode(), result.stderr()));
    }
    validateSidecar(out);
    return new ExperimentRef(req.id(), out.resolve(SIDECAR).toString(), "draft", null);
  }

  public JsonNode get(String id, String slice) {
    return adapter.experimentRead(requireDir(id).toString(), slice);
  }

  public ExperimentRef update(String id, UpdateExperimentRequest req) {
    Path dir = requireDir(id);
    Path sidecar = dir.resolve(SIDECAR);
    try {
      Files.writeString(sidecar, req.yaml());
    } catch (IOException e) {
      throw new CliException(40, "cannot write sidecar: " + e.getMessage());
    }
    JsonNode read = validateSidecar(dir);
    String status = read.path("experiment").path("status").asText("draft");
    return new ExperimentRef(id, sidecar.toString(), status, null);
  }

  public ExperimentRef addArms(String id, AddExperimentArmsRequest req) {
    Path dir = requireDir(id);
    requireSidecar(dir);
    List<String> args = new ArrayList<>();
    args.add("experiment");
    args.add("arm");
    args.add("add");
    args.add(dir.toString());
    args.addAll(req.presets());
    ProcessResult result = cli.runHarness(args);
    if (result.exitCode() != 0) {
      throw new CliException(
          result.exitCode(),
          ExitCodeMapper.clientMessage(result.exitCode(), result.stderr()));
    }
    JsonNode read = adapter.experimentRead(dir.toString(), null);
    String status = read.path("experiment").path("status").asText("draft");
    return new ExperimentRef(id, dir.resolve(SIDECAR).toString(), status, null);
  }

  public ExperimentRunProjection project(String id, ExperimentRunRequest req) {
    validateSandbox(id, req);
    Path dir = requireDir(id);
    requireSidecar(dir);
    JsonNode missing = adapter.experimentMissing(dir.toString(), req.slice());
    List<String> args = buildExperimentRunArgs(id, req, false);
    ProcessResult result = cli.runHarness(args, harnessEnv(id));
    if (result.exitCode() != ExitCodeMapper.DECLINED && result.exitCode() != ExitCodeMapper.SUCCESS) {
      throw new CliException(
          result.exitCode(),
          ExitCodeMapper.clientMessage(result.exitCode(), result.stderr()));
    }
    JsonNode read = adapter.experimentRead(dir.toString(), req.slice());
    List<String> scheduled = new ArrayList<>();
    read.path("experiment").path("run_plan").path("include").path("presets")
        .forEach(n -> scheduled.add(n.asText()));
    return new ExperimentRunProjection(
        result.stdout() == null ? "" : result.stdout(),
        result.exitCode() == 0 ? 1 : result.exitCode(),
        HarnessCli.extractStderrNames(result.stderr()),
        missing.path("missing_cells").asInt(0),
        read.path("coverage").path("voided_cells").asInt(0),
        req.slice(),
        List.copyOf(scheduled));
  }

  public RunJob start(String id, ExperimentRunRequest req) {
    if (req.approve() == null || !req.approve()) {
      throw new CliException(2, 400, "approve must be true to start a run");
    }
    validateSandbox(id, req);
    Path dir = requireDir(id);
    requireSidecar(dir);
    RunJob job = jobs.createQueued(id, dir);
    List<String> args = buildExperimentRunArgs(id, req, true);
    Path console = jobs.consoleLog(id);
    var inject = harnessEnv(id);
    Process process = cli.startHarness(args, console, inject);
    job = jobs.markRunning(id, process);
    Process finalProcess = process;
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

  public JsonNode coverage(String id, String slice) {
    return adapter.experimentCoverage(requireDir(id).toString(), slice);
  }

  public List<ReportSnapshotRef> listReports(String id) {
    JsonNode read = adapter.experimentRead(requireDir(id).toString(), null);
    List<ReportSnapshotRef> out = new ArrayList<>();
    read.path("experiment").path("report_snapshots").forEach(n -> out.add(
        new ReportSnapshotRef(
            n.path("at").asText(),
            n.path("status").asText(null),
            n.path("path").asText(null),
            n.path("ledger_rows").asInt(0))));
    return out;
  }

  public ReportSnapshotRef snapshot(String id) {
    JsonNode result = adapter.experimentSnapshot(requireDir(id).toString());
    JsonNode snap = result.path("snapshot");
    return new ReportSnapshotRef(
        snap.path("at").asText(),
        snap.path("status").asText(null),
        snap.path("path").asText(null),
        snap.path("ledger_rows").asInt(0));
  }

  private Map<String, String> harnessEnv(String id) {
    JsonNode exp = adapter.experimentRead(requireDir(id).toString(), null).path("experiment");
    String provider = exp.path("llm_provider").asText(ProviderCatalogService.OPENAI);
    String model = exp.path("run_plan").path("base").path("model").asText(null);
    Map<String, String> env = new LinkedHashMap<>(providers.envForExperiment(provider, model));
    env.putAll(secrets.loadGenerateEnv(id));
    return env;
  }

  private List<String> buildExperimentRunArgs(String id, ExperimentRunRequest req, boolean approve) {
    Path dir = props.resultsDir().resolve(id);
    List<String> args = new ArrayList<>();
    args.add("experiment");
    args.add("run");
    args.add(dir.toString());
    if (req.slice() != null && !req.slice().isBlank()) {
      args.add("--slice");
      args.add(req.slice());
    }
    if (req.concurrency() != null && req.concurrency() > 0) {
      args.add("--concurrency");
      args.add(String.valueOf(req.concurrency()));
    }
    if (approve) {
      args.add("--yes");
      args.add("--stream");
    }
    if (props.getDiskReserveGb() != null) {
      args.add("--disk-reserve-gb");
      args.add(String.valueOf(props.getDiskReserveGb()));
    }
    return args;
  }

  private void validateSandbox(String id, ExperimentRunRequest req) {
    if (req.allowCodeSandbox() != null && req.allowCodeSandbox()) {
      return;
    }
    JsonNode read = adapter.experimentRead(requireDir(id).toString(), req.slice());
    read.path("experiment").path("run_plan").path("include").path("presets")
        .forEach(n -> {
          String p = n.asText("").toUpperCase(Locale.ROOT);
          if (p.equals("D1") || p.equals("D2") || p.startsWith("D1") || p.startsWith("D2")) {
            throw new CliException(2, 400, "presets D1/D2 require allowCodeSandbox=true");
          }
        });
  }

  private JsonNode validateSidecar(Path dir) {
    return adapter.experimentRead(dir.toString(), null);
  }

  private Path requireDir(String id) {
    Path dir = props.resultsDir().resolve(id);
    if (Files.isDirectory(dir) && Files.isRegularFile(dir.resolve(SIDECAR))) {
      return dir;
    }
    // Soft resolve: unique sidecar whose experiment.id matches (legacy links /
    // plan-id URLs when the results dir was renamed).
    Path byPlan = findUniqueDirByPlanId(id);
    if (byPlan != null) {
      return byPlan;
    }
    throw new CliException(2, 404, "unknown experiment: " + id);
  }

  private Path findUniqueDirByPlanId(String planId) {
    Path results = props.resultsDir();
    if (!Files.isDirectory(results) || planId == null || planId.isBlank()) {
      return null;
    }
    List<Path> matches = new ArrayList<>();
    try (var stream = Files.list(results)) {
      stream.filter(Files::isDirectory).forEach(candidate -> {
        if (!Files.isRegularFile(candidate.resolve(SIDECAR))) {
          return;
        }
        try {
          JsonNode exp = adapter.experimentRead(candidate.toString(), null).path("experiment");
          if (planId.equals(exp.path("id").asText(null))) {
            matches.add(candidate);
          }
        } catch (CliException ignored) {
          // skip
        }
      });
    } catch (IOException e) {
      return null;
    }
    if (matches.size() == 1) {
      return matches.get(0);
    }
    return null;
  }

  private void requireSidecar(Path dir) {
    if (!Files.isRegularFile(dir.resolve(SIDECAR))) {
      throw new CliException(2, 404, "no experiment.yaml in " + dir.getFileName());
    }
  }

  public void delete(String id) {
    Path dir = props.resultsDir().resolve(id);
    requireSidecar(dir);
    jobs.cancelForDelete(id);
    DiskDelete.deleteTree(dir);
    DiskDelete.deleteTree(props.jobsDir().resolve(id));
  }

  private static Instant parseInstant(String raw) {
    if (raw == null || raw.isBlank()) {
      return null;
    }
    try {
      return Instant.parse(raw);
    } catch (Exception e) {
      return null;
    }
  }
}
