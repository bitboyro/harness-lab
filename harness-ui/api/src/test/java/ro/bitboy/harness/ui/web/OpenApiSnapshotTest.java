package ro.bitboy.harness.ui.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * Exports {@code /v3/api-docs} for {@code skill/openapi.snapshot.json}.
 *
 * <pre>
 * UPDATE_SNAPSHOT=1 ./mvnw -Dtest=OpenApiSnapshotTest test
 * </pre>
 */
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiSnapshotTest {

  private static final Path SNAPSHOT = Path.of("..", "skill", "openapi.snapshot.json")
      .toAbsolutePath()
      .normalize();

  @DynamicPropertySource
  static void props(DynamicPropertyRegistry registry) {
    registry.add("harness.data", () -> System.getProperty("java.io.tmpdir"));
    registry.add("harness.cli", () -> "harness");
    registry.add("harness.adapter", () -> "python3");
    registry.add("harness.adapter-script", () -> "/tmp/missing-adapter.py");
    registry.add("server.port", () -> "0");
  }

  @Autowired
  MockMvc mvc;

  @Autowired
  ObjectMapper mapper;

  @Test
  void openapiSnapshotMatchesLiveApiDocs() throws Exception {
    MvcResult result = mvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn();
    JsonNode live = mapper.readTree(result.getResponse().getContentAsByteArray());

    if ("1".equals(System.getenv("UPDATE_SNAPSHOT"))) {
      Files.createDirectories(SNAPSHOT.getParent());
      Files.writeString(
          SNAPSHOT,
          mapper.writerWithDefaultPrettyPrinter().writeValueAsString(live) + "\n",
          StandardCharsets.UTF_8);
      return;
    }

    if (!Files.isRegularFile(SNAPSHOT)) {
      throw new AssertionError(
          "missing " + SNAPSHOT + " — run UPDATE_SNAPSHOT=1 ./mvnw -Dtest=OpenApiSnapshotTest test");
    }
    JsonNode committed = mapper.readTree(Files.readString(SNAPSHOT));
    if (!committed.equals(live)) {
      throw new AssertionError(
          "skill/openapi.snapshot.json is stale — run UPDATE_SNAPSHOT=1 ./mvnw -Dtest=OpenApiSnapshotTest test");
    }
  }
}
