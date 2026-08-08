package ro.bitboy.harness.ui.core;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class DefaultProcessRunner implements ProcessRunner {

  private static final long DEFAULT_TIMEOUT_MINUTES = 30;

  @Override
  public ProcessResult run(List<String> command, Path workDir, Map<String, String> env) {
    try {
      ProcessBuilder pb = new ProcessBuilder(command);
      if (workDir != null) {
        pb.directory(workDir.toFile());
      }
      pb.environment().putAll(env);
      Process process = pb.start();
      // Close stdin so CLI confirm gates that read stdin fail closed (exit 1).
      process.getOutputStream().close();
      byte[] outBytes = process.getInputStream().readAllBytes();
      byte[] errBytes = process.getErrorStream().readAllBytes();
      boolean finished = process.waitFor(DEFAULT_TIMEOUT_MINUTES, TimeUnit.MINUTES);
      if (!finished) {
        process.destroyForcibly();
        throw new CliException(40, "subprocess timed out after " + DEFAULT_TIMEOUT_MINUTES + "m");
      }
      return new ProcessResult(
          process.exitValue(),
          new String(outBytes, StandardCharsets.UTF_8),
          new String(errBytes, StandardCharsets.UTF_8));
    } catch (CliException e) {
      throw e;
    } catch (IOException | InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new CliException(40, "failed to spawn process: " + e.getMessage());
    }
  }

  @Override
  public Process start(List<String> command, Path workDir, Map<String, String> env, Path consoleLog) {
    try {
      if (consoleLog != null) {
        Files.createDirectories(consoleLog.getParent());
        if (!Files.exists(consoleLog)) {
          Files.createFile(consoleLog);
        }
      }
      ProcessBuilder pb = new ProcessBuilder(command);
      if (workDir != null) {
        pb.directory(workDir.toFile());
      }
      pb.environment().putAll(env);
      pb.redirectErrorStream(true);
      Process process = pb.start();
      process.getOutputStream().close();
      if (consoleLog != null) {
        Thread t = new Thread(() -> drainTo(process.getInputStream(), consoleLog), "console-" + process.pid());
        t.setDaemon(true);
        t.start();
      }
      return process;
    } catch (IOException e) {
      throw new CliException(40, "failed to start process: " + e.getMessage());
    }
  }

  private static void drainTo(InputStream in, Path consoleLog) {
    try (OutputStream out = Files.newOutputStream(
        consoleLog, StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
      in.transferTo(out);
    } catch (IOException ignored) {
      // Process exit is authoritative; a torn console log is non-fatal.
    }
  }
}
