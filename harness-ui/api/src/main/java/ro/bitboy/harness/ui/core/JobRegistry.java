package ro.bitboy.harness.ui.core;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.dto.RunJob;

/**
 * Tracks owned harness run processes. Persistence: {@code jobs/<id>/job.json}
 * + {@code console.log}. Disk alone cannot prove liveness — {@link #isAlive}
 * reads the process handle.
 */
@Component
public class JobRegistry {

  private final HarnessProperties props;
  private final ObjectMapper mapper;
  private final Map<String, Process> live = new ConcurrentHashMap<>();

  public JobRegistry(HarnessProperties props) {
    this.props = props;
    this.mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
  }

  public Path jobDir(String id) {
    return props.jobsDir().resolve(id);
  }

  public Path jobJson(String id) {
    return jobDir(id).resolve("job.json");
  }

  public Path consoleLog(String id) {
    return jobDir(id).resolve("console.log");
  }

  public RunJob createQueued(String id, Path outDir) {
    RunJob job = new RunJob(
        id,
        RunJob.Status.queued,
        null,
        null,
        outDir.toString(),
        Instant.now(),
        null,
        null,
        null);
    persist(job);
    return job;
  }

  public RunJob markRunning(String id, Process process) {
    live.put(id, process);
    RunJob current = require(id);
    RunJob updated = current.withStatus(RunJob.Status.running)
        .withPid(process.pid())
        .withStartedAt(current.startedAt() != null ? current.startedAt() : Instant.now());
    persist(updated);
    return updated;
  }

  public RunJob markTerminal(String id, int exitCode, String errorKind, String message) {
    Process p = live.remove(id);
    if (p != null && p.isAlive()) {
      p.destroyForcibly();
    }
    RunJob.Status status = ExitCodeMapper.toJobStatus(exitCode);
    RunJob current = require(id);
    RunJob updated = current
        .withStatus(status)
        .withExitCode(exitCode)
        .withFinishedAt(Instant.now())
        .withErrorKind(errorKind)
        .withMessage(message);
    persist(updated);
    return updated;
  }

  /** Stop an owned process and drop the handle — used before deleting job dirs. */
  public void cancelForDelete(String id) {
    Process p = live.remove(id);
    if (p != null && p.isAlive()) {
      p.destroyForcibly();
    }
  }

  public Optional<RunJob> find(String id) {
    Path path = jobJson(id);
    if (!Files.isRegularFile(path)) {
      return Optional.empty();
    }
    try {
      return Optional.of(mapper.readValue(path.toFile(), RunJob.class));
    } catch (IOException e) {
      throw new CliException(40, "unreadable job.json for " + id);
    }
  }

  public RunJob require(String id) {
    return find(id).orElseThrow(() -> new CliException(2, 404, "unknown run: " + id));
  }

  /** True while the owned process handle is alive. */
  public boolean isAlive(String id) {
    Process p = live.get(id);
    if (p != null) {
      if (p.isAlive()) {
        return true;
      }
      // Reap: process exited since last poll.
      int code = p.exitValue();
      if (find(id).map(j -> j.status() == RunJob.Status.running || j.status() == RunJob.Status.queued)
          .orElse(false)) {
        markTerminal(id, code, null, messageForExit(id, code));
      }
      return false;
    }
    // Fall back to OS pid check if we restarted the API mid-run.
    return find(id)
        .filter(j -> j.pid() != null)
        .filter(j -> j.status() == RunJob.Status.running)
        .map(j -> ProcessHandle.of(j.pid()).map(ProcessHandle::isAlive).orElse(false))
        .orElse(false);
  }

  public boolean isTerminal(String id) {
    Optional<RunJob> job = find(id);
    if (job.isEmpty()) {
      return true;
    }
    RunJob j = job.get();
    if (j.status().isTerminal()) {
      return true;
    }
    return !isAlive(id) && j.status() != RunJob.Status.queued;
  }

  public void persist(RunJob job) {
    try {
      Path dir = jobDir(job.id());
      Files.createDirectories(dir);
      mapper.writerWithDefaultPrettyPrinter().writeValue(jobJson(job.id()).toFile(), job);
    } catch (IOException e) {
      throw new CliException(40, "cannot write job.json: " + e.getMessage());
    }
  }

  private String readConsoleTail(String id) {
    try {
      Path log = consoleLog(id);
      if (!Files.isRegularFile(log)) {
        return "";
      }
      String all = Files.readString(log);
      int n = all.length();
      return n <= 2000 ? all : all.substring(n - 2000);
    } catch (IOException e) {
      return "";
    }
  }

  /** Map exit code + drained console.log to a one-line UI message. */
  public String messageForExit(String id, int exitCode) {
    return ExitCodeMapper.clientMessage(exitCode, readConsoleTail(id));
  }
}
