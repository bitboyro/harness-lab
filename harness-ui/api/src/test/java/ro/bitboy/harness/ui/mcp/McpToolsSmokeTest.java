package ro.bitboy.harness.ui.mcp;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import ro.bitboy.harness.ui.Capabilities;

@SpringBootTest
@AutoConfigureMockMvc
class McpToolsSmokeTest {

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

  @Test
  void toolsListIncludesExperimentCapabilities() throws Exception {
    MvcResult result = mvc.perform(post("/mcp")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"jsonrpc\":\"2.0\",\"method\":\"tools/list\",\"id\":1}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.result.tools").isArray())
        .andReturn();

    var names = JsonPath.<java.util.List<String>>read(
        result.getResponse().getContentAsString(), "$.result.tools[*].name");
    org.junit.jupiter.api.Assertions.assertTrue(names.contains(Capabilities.LIST_EXPERIMENTS));
    org.junit.jupiter.api.Assertions.assertTrue(names.contains(Capabilities.SNAPSHOT_EXPERIMENT_REPORT));
    org.junit.jupiter.api.Assertions.assertTrue(names.contains(Capabilities.START_GENERATE));
    org.junit.jupiter.api.Assertions.assertTrue(names.contains(Capabilities.GET_LLM_CONFIG));
    org.junit.jupiter.api.Assertions.assertTrue(names.contains(Capabilities.UPSERT_PROVIDER));
    org.junit.jupiter.api.Assertions.assertEquals(48, names.size(), () -> "expected 48 frozen capabilities");
  }

  @Test
  void listTargetsToolCall() throws Exception {
    mvc.perform(post("/mcp")
            .contentType(MediaType.APPLICATION_JSON)
            .content(
                "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"id\":2,"
                    + "\"params\":{\"name\":\"list_targets\",\"arguments\":{}}}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.result.content[0].type").value("text"))
        .andExpect(jsonPath("$.result.content[0].text").value("[]"));
  }
}
