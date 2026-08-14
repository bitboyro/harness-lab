package ro.bitboy.harness.ui.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.HarnessCli;
import ro.bitboy.harness.ui.core.ProcessResult;
import ro.bitboy.harness.ui.core.ProcessRunner;
import ro.bitboy.harness.ui.dto.CompareRequest;
import ro.bitboy.harness.ui.dto.CompareResult;

class CompareServiceTest {

  @TempDir
  Path data;

  ProcessRunner runner;
  CompareService service;

  @BeforeEach
  void setUp() throws Exception {
    HarnessProperties props = new HarnessProperties();
    props.setData(data);
    Files.createDirectories(data.resolve("results/a"));
    Files.createDirectories(data.resolve("results/b"));
    Files.writeString(data.resolve("results/a/results.jsonl"), "{\"arm\":\"A1\"}\n");
    Files.writeString(data.resolve("results/b/results.jsonl"), "{\"arm\":\"A1\"}\n");

    runner = mock(ProcessRunner.class);
    HarnessCli cli = new HarnessCli(props, runner);

    // Minimal RunService stub via real class with mocks for unused deps — use a thin fake.
    RunService runs = mock(RunService.class);
    when(runs.resultsDir("a")).thenReturn(data.resolve("results/a"));
    when(runs.resultsDir("b")).thenReturn(data.resolve("results/b"));

    service = new CompareService(props, cli, runs);
  }

  @Test
  void exit3ReturnsHttp200ShapedRefusalPayload() {
    String refusal = """
        REFUSING TO POOL — these runs are not measuring the same thing:
          model: a=gpt-4o, b=gpt-5
        Deltas across this boundary are still shown, marked ‡, and are not findings:
        """;
    when(runner.run(anyList(), nullable(Path.class), anyMap()))
        .thenReturn(new ProcessResult(3, refusal, ""));

    CompareResult result = service.compare(new CompareRequest(List.of("a", "b")));

    assertTrue(result.refused());
    assertTrue(result.refusalText().contains("REFUSING TO POOL"));
    assertEquals("model", result.brokenBoundary());
    assertTrue(result.artifactDir().startsWith("compare/"));
  }

  @Test
  void extractBoundaryParsesParameterName() {
    assertEquals(
        "mcp_revision",
        CompareService.extractBoundary(
            "REFUSING TO POOL\n  mcp_revision: a=legacy, b=2026-07-28\n"));
    assertNull(CompareService.extractBoundary("ok"));
  }
}
