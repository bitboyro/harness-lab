package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;

/**
 * Spawns {@code harness mock serve} (HTTP stub + MCP gateway) for From-OpenAPI
 * when the user has no staging URL. Processes stay alive for the API JVM so
 * probe runs can still reach A-arms.
 */
@Service
public class MockSidecarService {

  private static final Duration READY_TIMEOUT = Duration.ofSeconds(20);
  private static final String READY_PREFIX = "MOCK_READY ";

  public record MockEndpoints(String httpUrl, String mcpUrl, long pid) {}

  private final HarnessProperties props;
  private final ObjectMapper json;
  private final ConcurrentHashMap<String, Process> live = new ConcurrentHashMap<>();

  public MockSidecarService(HarnessProperties props, ObjectMapper json) {
    this.props = props;
    this.json = json;
  }

  public MockEndpoints startForJob(String jobId, Path openApiSpec, Path workspace) {
    stop(jobId);
    List<String> cmd = new ArrayList<>();
    cmd.add(props.getCli());
    cmd.add("mock");
    cmd.add("serve");
    cmd.add("--spec");
    cmd.add(openApiSpec.toAbsolutePath().normalize().toString());
    cmd.add("--host");
    cmd.add("127.0.0.1");

    ProcessBuilder pb = new ProcessBuilder(cmd);
    pb.redirectErrorStream(true);
    try {
      Path log = workspace.resolve("mock-sidecar.log");
      Files.createDirectories(workspace);
      Process process = pb.start();
      live.put(jobId, process);
      MockEndpoints endpoints = awaitReady(process, log);
      Files.writeString(
          workspace.resolve("mock.json"),
          json.writeValueAsString(Map.of(
              "httpUrl", endpoints.httpUrl(),
              "mcpUrl", endpoints.mcpUrl(),
              "pid", endpoints.pid())),
          StandardCharsets.UTF_8);
      return endpoints;
    } catch (IOException e) {
      stop(jobId);
      throw new CliException(40, "cannot start local mock sidecars: " + e.getMessage());
    }
  }

  public void stop(String jobId) {
    Process p = live.remove(jobId);
    if (p != null && p.isAlive()) {
      p.destroy();
      try {
        p.waitFor(3, TimeUnit.SECONDS);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
      }
      if (p.isAlive()) {
        p.destroyForcibly();
      }
    }
  }

  private MockEndpoints awaitReady(Process process, Path log) throws IOException {
    StringBuilder captured = new StringBuilder();
    BufferedReader reader = new BufferedReader(
        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
    long deadline = System.nanoTime() + READY_TIMEOUT.toNanos();
    try {
      while (System.nanoTime() < deadline) {
        if (!process.isAlive()) {
          // Read whatever is left
          while (reader.ready()) {
            String rest = reader.readLine();
            if (rest == null) {
              break;
            }
            captured.append(rest).append('\n');
          }
          Files.writeString(log, captured.toString(), StandardCharsets.UTF_8);
          throw new CliException(40, "mock sidecar exited before READY");
        }
        String line = reader.readLine();
        if (line == null) {
          break;
        }
        captured.append(line).append('\n');
        if (line.startsWith(READY_PREFIX)) {
          String payload = line.substring(READY_PREFIX.length()).trim();
          JsonNode node = json.readTree(payload);
          String httpUrl = node.path("httpUrl").asText(null);
          String mcpUrl = node.path("mcpUrl").asText(null);
          if (httpUrl == null || httpUrl.isBlank() || mcpUrl == null || mcpUrl.isBlank()) {
            throw new CliException(40, "mock READY missing httpUrl/mcpUrl");
          }
          Thread drain = new Thread(() -> drainRest(reader, log, captured), "mock-drain");
          drain.setDaemon(true);
          drain.start();
          return new MockEndpoints(httpUrl, mcpUrl, process.pid());
        }
      }
    } catch (CliException e) {
      throw e;
    } catch (IOException e) {
      Files.writeString(log, captured.toString(), StandardCharsets.UTF_8);
      throw e;
    }
    Files.writeString(log, captured.toString(), StandardCharsets.UTF_8);
    throw new CliException(40, "timed out waiting for mock MOCK_READY line");
  }

  private static void drainRest(BufferedReader reader, Path log, StringBuilder head) {
    try {
      StringBuilder all = new StringBuilder(head);
      String line;
      while ((line = reader.readLine()) != null) {
        all.append(line).append('\n');
      }
      Files.writeString(log, all.toString(), StandardCharsets.UTF_8);
    } catch (IOException ignored) {
      // process ended
    }
  }
}
