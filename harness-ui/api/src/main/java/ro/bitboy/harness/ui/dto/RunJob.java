package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record RunJob(
    String id,
    Status status,
    Long pid,
    Integer exitCode,
    String outDir,
    Instant startedAt,
    Instant finishedAt,
    String errorKind,
    String message
) {

  public enum Status {
    queued, running, succeeded, failed, cancelled, declined;

    public boolean isTerminal() {
      return this == succeeded || this == failed || this == cancelled || this == declined;
    }
  }

  public RunJob withStatus(Status s) {
    return new RunJob(id, s, pid, exitCode, outDir, startedAt, finishedAt, errorKind, message);
  }

  public RunJob withPid(Long p) {
    return new RunJob(id, status, p, exitCode, outDir, startedAt, finishedAt, errorKind, message);
  }

  public RunJob withExitCode(Integer c) {
    return new RunJob(id, status, pid, c, outDir, startedAt, finishedAt, errorKind, message);
  }

  public RunJob withStartedAt(Instant t) {
    return new RunJob(id, status, pid, exitCode, outDir, t, finishedAt, errorKind, message);
  }

  public RunJob withFinishedAt(Instant t) {
    return new RunJob(id, status, pid, exitCode, outDir, startedAt, t, errorKind, message);
  }

  public RunJob withErrorKind(String k) {
    return new RunJob(id, status, pid, exitCode, outDir, startedAt, finishedAt, k, message);
  }

  public RunJob withMessage(String m) {
    return new RunJob(id, status, pid, exitCode, outDir, startedAt, finishedAt, errorKind, m);
  }
}
