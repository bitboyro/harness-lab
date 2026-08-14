package ro.bitboy.harness.ui.web;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.hamcrest.Matchers;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import ro.bitboy.harness.ui.core.ProcessResult;
import ro.bitboy.harness.ui.core.ProcessRunner;

/**
 * Documents the curl path for T2.3 without requiring a live harness binary:
 *
 * <pre>
 * curl -sS -F file=@examples/openapi.json http://127.0.0.1:8085/api/v1/targets
 * </pre>
 */
@SpringBootTest
@AutoConfigureMockMvc
class CurlPathSmokeTest {

  private static final Path DATA_DIR = Path.of(
      System.getProperty("java.io.tmpdir"),
      "harness-ui-api-test-" + UUID.randomUUID());

  @DynamicPropertySource
  static void props(DynamicPropertyRegistry registry) throws Exception {
    Files.createDirectories(DATA_DIR);
    registry.add("harness.data", DATA_DIR::toString);
    registry.add("harness.cli", () -> "harness");
    registry.add("harness.adapter", () -> "python3");
    registry.add("harness.adapter-script", () -> "/tmp/missing-adapter.py");
    registry.add("server.port", () -> "0");
  }

  @Autowired
  MockMvc mvc;

  @MockBean
  ProcessRunner processRunner;

  @BeforeEach
  void stubRunner() {
    when(processRunner.run(anyList(), nullable(Path.class), anyMap()))
        .thenReturn(new ProcessResult(0, "{\"harness_version\":\"0.0.1\",\"valid\":true}", ""));
  }

  @Test
  void uploadContractMatchesCurlMultipartPath() throws Exception {
    MockMultipartFile file = new MockMultipartFile(
        "file",
        "openapi.json",
        "application/json",
        "{\"openapi\":\"3.0.0\",\"info\":{\"title\":\"demo\",\"version\":\"0\"},\"paths\":{}}"
            .getBytes(StandardCharsets.UTF_8));

    MvcResult result = mvc.perform(multipart("/api/v1/targets").file(file))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.id").isNotEmpty())
        .andExpect(jsonPath("$.kind").value("openapi"))
        .andReturn();

    String id = JsonPath.read(result.getResponse().getContentAsString(), "$.id");
    assertTrue(Files.isRegularFile(DATA_DIR.resolve("targets").resolve(id).resolve("spec.json")));

    mvc.perform(get("/api/v1/targets"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0].id").value(id));
  }

  @Test
  void pathTraversalOnArtifactIs400() throws Exception {
    String runId = "r-smoke";
    Path runDir = DATA_DIR.resolve("results").resolve(runId);
    Files.createDirectories(runDir.resolve("artifacts"));
    Files.writeString(runDir.resolve("results.jsonl"), "{\"arm\":\"Z0\"}\n");
    Files.writeString(runDir.resolve("artifacts").resolve(".cache-rows"), "1");

    // Literal `..` segments (as after URL decode) must 400, not 404.
    mvc.perform(get("/api/v1/runs/{id}/artifacts/{name}", runId, "../../etc/passwd")
            .accept(MediaType.ALL))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").value(Matchers.containsString("traversal")));
  }

  @Test
  void compareRefusalShapeViaMockedProcess() throws Exception {
    Files.createDirectories(DATA_DIR.resolve("results/a"));
    Files.createDirectories(DATA_DIR.resolve("results/b"));
    Files.writeString(DATA_DIR.resolve("results/a/results.jsonl"), "{\"arm\":\"Z0\"}\n");
    Files.writeString(DATA_DIR.resolve("results/b/results.jsonl"), "{\"arm\":\"Z0\"}\n");

    when(processRunner.run(anyList(), nullable(Path.class), anyMap())).thenReturn(new ProcessResult(
        3,
        "REFUSING TO POOL — these runs are not measuring the same thing:\n  model: a=x, b=y\n",
        ""));

    mvc.perform(post("/api/v1/compare")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"runIds\":[\"a\",\"b\"]}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.refused").value(true))
        .andExpect(jsonPath("$.refusalText").value(Matchers.containsString("REFUSING TO POOL")))
        .andExpect(jsonPath("$.brokenBoundary").value("model"));
  }

  @Test
  void spaFallbackForwardsDeepLink() throws Exception {
    MvcResult result = mvc.perform(get("/app/deep/link"))
        .andExpect(status().isOk())
        .andReturn();
    String forwarded = result.getResponse().getForwardedUrl();
    String body = result.getResponse().getContentAsString();
    assertTrue(
        (forwarded != null && forwarded.contains("index.html"))
            || body.contains("harness-ui"));
  }

  @Test
  void experimentDeepLinkUsesShell() throws Exception {
    MvcResult result = mvc.perform(get("/experiments/my-run/"))
        .andExpect(status().isOk())
        .andReturn();
    assertTrue(
        result.getResponse().getForwardedUrl() != null
            && result.getResponse().getForwardedUrl().contains("experiments/_/index.html"));
  }

  @Test
  void experimentsIndexForwards() throws Exception {
    MvcResult result = mvc.perform(get("/experiments/"))
        .andExpect(status().isOk())
        .andReturn();
    assertTrue(
        result.getResponse().getForwardedUrl() != null
            && result.getResponse().getForwardedUrl().contains("experiments/index.html"));
  }

  @Test
  void artifactViewerShellForwardsDespiteFileExtension() throws Exception {
    MvcResult result = mvc.perform(get("/runs/local-smoke/artifacts/report.html/"))
        .andExpect(status().isOk())
        .andReturn();
    assertTrue(
        result.getResponse().getForwardedUrl() != null
            && result.getResponse().getForwardedUrl().contains("runs/_/artifacts/_/index.html"));
  }
}
