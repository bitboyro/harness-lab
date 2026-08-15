package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.core.ExitCodeMapper;
import ro.bitboy.harness.ui.core.HarnessCli;
import ro.bitboy.harness.ui.core.JobRegistry;
import ro.bitboy.harness.ui.core.PathsSafe;
import ro.bitboy.harness.ui.dto.ArtifactRef;
import ro.bitboy.harness.ui.dto.CreateExperimentFromGenerateRequest;
import ro.bitboy.harness.ui.dto.CreateExperimentRequest;
import ro.bitboy.harness.ui.dto.ExperimentRef;
import ro.bitboy.harness.ui.dto.GenerateJob;
import ro.bitboy.harness.ui.dto.GeneratePhases;
import ro.bitboy.harness.ui.dto.GenerateProgress;
import ro.bitboy.harness.ui.dto.GenerateStaging;
import ro.bitboy.harness.ui.dto.RunJob;
import ro.bitboy.harness.ui.dto.StartGenerateRequest;
import ro.bitboy.harness.ui.dto.Target;

@Service
public class GenerateService {

  private static final List<String> DEFAULT_PROBE_PRESETS =
      List.of("Z0", "A1", "A2", "C1", "D1");

  private final HarnessProperties props;
  private final HarnessCli cli;
  private final JobRegistry jobs;
  private final TargetService targets;
  private final PackService packs;
  private final AdapterService adapter;
  private final ExperimentService experiments;
  private final SecretsService secrets;
  private final MockSidecarService mocks;
  private final ObjectMapper json;
  private final ProviderCatalogService providers;

  public GenerateService(
      HarnessProperties props,
      HarnessCli cli,
      JobRegistry jobs,
      TargetService targets,
      PackService packs,
      AdapterService adapter,
      ExperimentService experiments,
      SecretsService secrets,
      MockSidecarService mocks,
      ObjectMapper json,
      ProviderCatalogService providers) {
    this.props = props;
    this.cli = cli;
    this.jobs = jobs;
    this.targets = targets;
    this.packs = packs;
    this.adapter = adapter;
    this.experiments = experiments;
    this.secrets = secrets;
    this.mocks = mocks;
    this.json = json;
    this.providers = providers;
  }

  public GenerateJob start(StartGenerateRequest req) {
    Target target = targets.require(req.targetId());
    if (!"openapi".equals(target.kind())) {
      throw new CliException(2, 400, "generate requires an OpenAPI target");
    }
    GeneratePhases phases = req.phases() == null ? new GeneratePhases(null, null, null, null, null) : req.phases();
    if (Boolean.TRUE.equals(phases.enrich())) {
      if (req.approveEnrich() == null || !req.approveEnrich()) {
        throw new CliException(2, 400, "approveEnrich must be true when enrich phase is enabled");
      }
    }
    Path workspace = workspace(req.jobId());
    if (Files.exists(workspace)) {
      throw new CliException(2, 409, "generate job already exists: " + req.jobId());
    }

    boolean useLocalMock = Boolean.TRUE.equals(req.useLocalMock());
    String mcpUrl = null;
    String mockHttpUrl = null;
    try {
      Files.createDirectories(workspace);
      Files.createDirectories(props.secretsDir());
      if (useLocalMock) {
        Path spec = targets.specOrUrlPath(req.targetId()).toAbsolutePath().normalize();
        MockSidecarService.MockEndpoints ends = mocks.startForJob(req.jobId(), spec, workspace);
        mockHttpUrl = ends.httpUrl();
        mcpUrl = ends.mcpUrl();
      } else if (req.mcpUrl() != null && !req.mcpUrl().isBlank()) {
        mcpUrl = req.mcpUrl().trim();
      }
      Files.writeString(workspace.resolve("generate.config.yaml"),
          buildConfigYaml(req, target, phases, useLocalMock, mcpUrl));
    } catch (IOException e) {
      if (useLocalMock) {
        mocks.stop(req.jobId());
      }
      throw new CliException(40, "cannot initialize generate workspace: " + e.getMessage());
    }

    Map<String, String> stagingEnv = stagingSecretValues(req, mockHttpUrl);
    secrets.writeGenerateEnv(req.jobId(), stagingEnv);
    Map<String, String> inject = new LinkedHashMap<>(
        providers.envFor(ProviderCatalogService.OPENAI, "gpt-5.6-luna"));
    inject.putAll(secrets.loadGenerateEnv(req.jobId()));

    jobs.createQueued(req.jobId(), workspace);
    List<String> args = List.of(
        "generate", "run", workspace.resolve("generate.config.yaml").toString(), "--yes");
    Path console = jobs.consoleLog(req.jobId());
    Process process = cli.startHarness(args, console, inject);
    jobs.markRunning(req.jobId(), process);
    Process finalProcess = process;
    String id = req.jobId();
    Thread waiter = new Thread(() -> {
      try {
        int code = finalProcess.waitFor();
        reapGenerateTerminal(id, code);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        jobs.markTerminal(id, ExitCodeMapper.CANCELLED, "cancelled", "interrupted");
      }
    }, "generate-wait-" + id);
    waiter.setDaemon(true);
    waiter.start();
    return toGenerateJob(jobs.require(req.jobId()));
  }

  public GenerateProgress progress(String jobId) {
    Path workspace = workspace(jobId);
    var existing = jobs.find(jobId);
    if (existing.isEmpty() && !Files.isDirectory(workspace)) {
      throw new CliException(2, 404, "unknown generate job: " + jobId);
    }
    jobs.isAlive(jobId);
    JsonNode envelope;
    try {
      envelope = adapter.generateStatus(workspace.toString());
    } catch (CliException e) {
      // Race: workspace exists but status.json not written yet.
      RunJob job = existing.orElseGet(() -> new RunJob(
          jobId,
          RunJob.Status.running,
          null,
          null,
          workspace.toString(),
          null,
          null,
          null,
          "waiting for status.json"));
      return new GenerateProgress(toGenerateJob(job), false, null, null);
    }
    RunJob job = existing.orElse(syntheticJob(jobId, workspace, envelope));
    boolean terminal = envelope.path("terminal").asBoolean(false)
        || job.status().isTerminal();
    return new GenerateProgress(
        toGenerateJob(job),
        terminal,
        envelope.path("status").isNull() ? null : envelope.path("status"),
        envelope.path("error").isNull() ? null : envelope.path("error"));
  }

  public JsonNode manifest(String jobId) {
    Path workspace = requireWorkspace(jobId);
    raiseIfGenerateFailed(jobId);
    try {
      JsonNode envelope = adapter.generateManifest(workspace.toString());
      return envelope.path("manifest");
    } catch (CliException e) {
      if (e.getHttpStatus() == 404 || e.getMessage().contains("no manifest")) {
        throw new CliException(2, 404, "manifest not ready for job: " + jobId);
      }
      throw e;
    }
  }

  public List<ArtifactRef> listArtifacts(String jobId) {
    Path root = requireWorkspace(jobId);
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
              "generate/" + jobId + "/" + rel.toString().replace('\\', '/'),
              Files.size(p)));
        } catch (IOException ignored) {
          // skip
        }
      });
    } catch (IOException e) {
      throw new CliException(40, "cannot list generate artifacts: " + e.getMessage());
    }
    return out;
  }

  public ResponseEntity<Resource> getArtifact(String jobId, String name) {
    Path file = PathsSafe.resolveUnder(requireWorkspace(jobId), name);
    if (!Files.isRegularFile(file)) {
      throw new CliException(2, 404, "artifact not found: " + name);
    }
    return ArtifactService.serve(file);
  }

  public ExperimentRef createExperiment(String jobId, CreateExperimentFromGenerateRequest req) {
    raiseIfGenerateFailed(jobId);
    Path workspace = requireWorkspace(jobId);
    JsonNode manifest = manifest(jobId);
    String packRel = manifest.path("pack_path").asText(null);
    String packId = manifest.path("pack_id").asText(null);
    if (packRel == null || packRel.isBlank() || packId == null || packId.isBlank()) {
      throw new CliException(2, 400, "generate job has no pack; run fixtures+pack phases first");
    }
    Path packSrc = workspace.resolve(packRel);
    if (!Files.isRegularFile(packSrc)) {
      throw new CliException(2, 404, "pack file missing in workspace: " + packRel);
    }
    Path packDest = packs.packPath(packId);
    try {
      Files.createDirectories(packDest.getParent());
      Files.copy(packSrc, packDest, StandardCopyOption.REPLACE_EXISTING);
    } catch (IOException e) {
      throw new CliException(40, "cannot copy pack: " + e.getMessage());
    }

    List<String> presets = new ArrayList<>();
    manifest.path("arms_probe").forEach(n -> presets.add(n.asText()));
    if (presets.isEmpty()) {
      presets.addAll(DEFAULT_PROBE_PRESETS);
    }

    String yaml = buildExperimentYaml(
        req.experimentId(),
        jobId,
        packDest.toAbsolutePath().toString(),
        presets,
        req.planOverrides());
    ExperimentRef created = experiments.create(new CreateExperimentRequest(req.experimentId(), yaml, null));
    // Carry staging / mock base URL into the experiment id secrets file so
    // probe runs inherit TARGET_BASE_URL without re-entering the wizard.
    Map<String, String> staging = secrets.loadGenerateEnv(jobId);
    if (!staging.isEmpty()) {
      secrets.writeGenerateEnv(req.experimentId(), staging);
    }
    return created;
  }

  private Path workspace(String jobId) {
    return props.generateDir().resolve(jobId);
  }

  private void reapGenerateTerminal(String jobId, int processExit) {
    Path errFile = workspace(jobId).resolve("errors.json");
    if (Files.isRegularFile(errFile)) {
      try {
        JsonNode err = json.readTree(errFile.toFile());
        int exit = err.path("exit_code").asInt(processExit == 0 ? ExitCodeMapper.ARGUMENT : processExit);
        String msg = ExitCodeMapper.messageFromGenerateError(err);
        if (msg.isBlank()) {
          msg = jobs.messageForExit(jobId, exit);
        }
        String kind = err.path("kind").asText(null);
        jobs.markTerminal(jobId, exit, kind, msg);
        return;
      } catch (IOException ignored) {
        // fall through to process exit
      }
    }
    jobs.markTerminal(jobId, processExit, null, jobs.messageForExit(jobId, processExit));
  }

  /** Surface structured generate failures as HTTP 400/503 (G4.5). */
  private void raiseIfGenerateFailed(String jobId) {
    Path errFile = workspace(jobId).resolve("errors.json");
    if (!Files.isRegularFile(errFile)) {
      return;
    }
    try {
      JsonNode err = json.readTree(errFile.toFile());
      throw ExitCodeMapper.fromGenerateError(err);
    } catch (CliException e) {
      throw e;
    } catch (IOException e) {
      throw new CliException(40, "cannot read generate errors.json: " + e.getMessage());
    }
  }

  private static Map<String, String> stagingSecretValues(
      StartGenerateRequest req, String mockHttpUrl) {
    Map<String, String> env = new LinkedHashMap<>();
    GenerateStaging staging = req.staging();
    if (staging == null && mockHttpUrl == null) {
      return env;
    }
    String baseUrlEnv = "TARGET_BASE_URL";
    if (staging != null && staging.baseUrlEnv() != null && !staging.baseUrlEnv().isBlank()) {
      baseUrlEnv = staging.baseUrlEnv();
    }
    if (mockHttpUrl != null && !mockHttpUrl.isBlank()) {
      env.put(baseUrlEnv, mockHttpUrl);
    } else if (staging != null && staging.baseUrl() != null && !staging.baseUrl().isBlank()) {
      env.put(baseUrlEnv, staging.baseUrl());
    }
    if (staging != null
        && staging.authEnv() != null
        && !staging.authEnv().isBlank()
        && staging.authToken() != null
        && !staging.authToken().isBlank()) {
      env.put(staging.authEnv(), staging.authToken());
    }
    return env;
  }

  private Path requireWorkspace(String jobId) {
    Path workspace = workspace(jobId);
    if (!Files.isDirectory(workspace) && jobs.find(jobId).isEmpty()) {
      throw new CliException(2, 404, "unknown generate job: " + jobId);
    }
    return workspace;
  }

  private static GenerateJob toGenerateJob(RunJob job) {
    String status = switch (job.status()) {
      case queued -> "accepted";
      case running -> "running";
      case succeeded -> "complete";
      case failed, cancelled, declined -> "failed";
    };
    Path out = Path.of(job.outDir());
    String workspace = out.getFileName() != null
        ? "generate/" + out.getFileName()
        : job.outDir();
    return new GenerateJob(job.id(), status, workspace);
  }

  private static RunJob syntheticJob(String jobId, Path workspace, JsonNode envelope) {
    boolean terminal = envelope.path("terminal").asBoolean(false);
    JsonNode err = envelope.path("error");
    RunJob.Status status = RunJob.Status.running;
    if (terminal) {
      if (err.isNull() || err.isMissingNode()) {
        status = RunJob.Status.succeeded;
      } else {
        status = RunJob.Status.failed;
      }
    }
    return new RunJob(
        jobId,
        status,
        null,
        err.isNull() || err.isMissingNode() ? null : err.path("exit_code").asInt(),
        workspace.toString(),
        null,
        null,
        err.isNull() || err.isMissingNode() ? null : err.path("kind").asText(null),
        null);
  }

  private String buildConfigYaml(
      StartGenerateRequest req,
      Target target,
      GeneratePhases phases,
      boolean useLocalMock,
      String mcpUrl) throws IOException {
    Path spec = targets.specOrUrlPath(req.targetId()).toAbsolutePath().normalize();
    String baseUrlEnv = req.staging().baseUrlEnv() != null && !req.staging().baseUrlEnv().isBlank()
        ? req.staging().baseUrlEnv()
        : "TARGET_BASE_URL";
    String packId = req.targetId().replaceAll("^t-", "") + "-gen";
    StringBuilder sb = new StringBuilder();
    sb.append("schema_version: 1\n");
    sb.append("job_id: ").append(yamlScalar(req.jobId())).append('\n');
    // A customer mcpUrl implies gateway available even if the checkbox was omitted.
    boolean mcpGateway = useLocalMock
        || Boolean.TRUE.equals(req.mcpGateway())
        || (mcpUrl != null && !mcpUrl.isBlank());
    sb.append("mcp_gateway: ").append(mcpGateway).append('\n');
    if (mcpUrl != null && !mcpUrl.isBlank()) {
      sb.append("mcp_url: ").append(yamlScalar(mcpUrl)).append('\n');
    }
    sb.append("\ntarget:\n");
    sb.append("  spec: ").append(yamlScalar(spec.toString())).append('\n');
    sb.append("  id: ").append(yamlScalar(req.targetId())).append('\n');
    sb.append("  base_url_env: ").append(yamlScalar(baseUrlEnv)).append('\n');
    if (req.staging().seed() != null) {
      sb.append("  seed: ").append(req.staging().seed()).append('\n');
    }
    if (req.staging().authEnv() != null && !req.staging().authEnv().isBlank()) {
      sb.append("  auth:\n");
      sb.append("    type: bearer\n");
      sb.append("    env: ").append(yamlScalar(req.staging().authEnv())).append('\n');
    }
    sb.append("\nphases:\n");
    sb.append("  analyze: ").append(phaseFlag(phases.analyze(), true)).append('\n');
    if (Boolean.TRUE.equals(phases.enrich())) {
      sb.append("  enrich:\n");
      sb.append("    model: gpt-5.6-luna\n");
      sb.append("    max_usd: 2.0\n");
    } else {
      sb.append("  enrich: false\n");
    }
    if (phaseFlag(phases.materials(), true)) {
      sb.append("  materials:\n");
      sb.append("    doc_budget: standard\n");
      if (mcpGateway) {
        sb.append("    presets: [Z0, A1, A2, C1, D1]\n");
      } else {
        // Field HTTP without MCP gateway — C1/D1/Z0 only (G6).
        sb.append("    presets: [Z0, C1, D1]\n");
      }
    } else {
      sb.append("  materials: false\n");
    }
    sb.append("  fixtures: ").append(phaseFlag(phases.fixtures(), true)).append('\n');
    sb.append("  pack: ").append(phaseFlag(phases.pack(), true)).append('\n');
    sb.append("\npack:\n");
    sb.append("  id: ").append(yamlScalar(packId)).append('\n');
    sb.append("  min_graded_tasks: 5\n");
    sb.append("  unanswerable_share: 0.15\n");
    sb.append("  report_class: field\n");
    sb.append("\noutput:\n");
    sb.append("  dir: .\n");
    return sb.toString();
  }

  private static boolean phaseFlag(Boolean value, boolean defaultValue) {
    return value == null ? defaultValue : value;
  }

  private static String yamlScalar(String raw) {
    if (raw == null) {
      return "null";
    }
    if (raw.isEmpty()
        || raw.indexOf(':') >= 0
        || raw.indexOf('#') >= 0
        || raw.startsWith("'")
        || raw.startsWith("\"")
        || raw.contains("\n")) {
      return "'" + raw.replace("'", "''") + "'";
    }
    return raw;
  }

  private static String buildExperimentYaml(
      String experimentId,
      String jobId,
      String packPath,
      List<String> presets,
      String planOverrides) {
    Instant now = Instant.now();
    StringBuilder sb = new StringBuilder();
    sb.append("schema_version: 1\n\n");
    sb.append("experiment:\n");
    sb.append("  id: ").append(yamlScalar(experimentId)).append('\n');
    sb.append("  status: draft\n");
    sb.append("  created_at: ").append(yamlScalar(now.toString())).append('\n');
    sb.append("  updated_at: ").append(yamlScalar(now.toString())).append('\n');
    sb.append("  llm_provider: openai\n");
    sb.append("  run_plan:\n");
    sb.append("    id: ").append(yamlScalar(experimentId)).append('\n');
    sb.append("    rationale: >\n");
    sb.append("      Field probe experiment created from OpenAPI onboarding job ")
        .append(jobId).append(".\n");
    sb.append("    base:\n");
    sb.append("      model: gpt-5.6-luna\n");
    sb.append("      reasoning_effort: low\n");
    sb.append("      temperature: 0.0\n");
    sb.append("      repeats: 1\n");
    sb.append("      mcp_revision: \"2026-07-28\"\n");
    sb.append("    include:\n");
    sb.append("      presets: [");
    sb.append(String.join(", ", presets));
    sb.append("]\n");
    sb.append("    tasks:\n");
    sb.append("      pack: ").append(yamlScalar(packPath)).append('\n');
    if (planOverrides != null && !planOverrides.isBlank()) {
      sb.append("\n  # planOverrides from create_experiment_from_generate\n");
      for (String line : planOverrides.split("\n")) {
        sb.append("  # ").append(line).append('\n');
      }
    }
    sb.append("  slices: {}\n");
    sb.append("  retired_arms: []\n");
    sb.append("  episodes: []\n");
    sb.append("  report_snapshots: []\n");
    return sb.toString();
  }
}
