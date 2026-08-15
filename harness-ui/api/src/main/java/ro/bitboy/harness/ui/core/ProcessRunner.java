package ro.bitboy.harness.ui.core;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/** Spawns OS processes. Mocked in unit tests. */
public interface ProcessRunner {

  /**
   * Run to completion, capturing stdout/stderr.
   *
   * @param command argv
   * @param workDir optional cwd (null = inherit)
   * @param env extra env vars (merged over process environment)
   */
  ProcessResult run(List<String> command, Path workDir, Map<String, String> env);

  default ProcessResult run(List<String> command) {
    return run(command, null, Map.of());
  }

  /**
   * Start a long-running process; caller owns lifecycle.
   *
   * @param consoleLog append stdout+stderr here
   * @return the live {@link Process}
   */
  Process start(List<String> command, Path workDir, Map<String, String> env, Path consoleLog);
}
