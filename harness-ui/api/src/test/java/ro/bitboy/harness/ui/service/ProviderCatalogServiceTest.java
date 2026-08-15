package ro.bitboy.harness.ui.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.dto.LlmConfig;
import ro.bitboy.harness.ui.dto.ProviderView;
import ro.bitboy.harness.ui.dto.RegisteredModel;
import ro.bitboy.harness.ui.dto.UpsertModelRequest;
import ro.bitboy.harness.ui.dto.UpsertProviderRequest;

class ProviderCatalogServiceTest {

  @TempDir
  Path data;

  ProviderCatalogService service;

  @BeforeEach
  void setUp() {
    HarnessProperties props = new HarnessProperties();
    props.setData(data);
    service = new ProviderCatalogService(props, new ObjectMapper());
  }

  @Test
  void emptyCatalogIncludesBuiltinOpenaiWithoutKey() {
    LlmConfig cfg = service.get();
    assertEquals(List.of("openai"), cfg.adapters());
    assertEquals(1, cfg.providers().size());
    ProviderView openai = cfg.providers().get(0);
    assertEquals("openai", openai.id());
    assertTrue(openai.builtin());
    assertFalse(openai.apiKeySet());
    assertNull(openai.apiKeyHint());
    assertEquals(1, openai.models().size());
    assertEquals("gpt-5.6-luna", openai.models().get(0).id());
  }

  @Test
  void upsertOpenaiStoresKeyWithoutEchoingIt() {
    ProviderView saved = service.upsertProvider(
        "openai",
        new UpsertProviderRequest(
            "OpenAI",
            "openai",
            "https://api.openai.com/v1",
            "sk-test-secret-key",
            List.of(new RegisteredModel("gpt-5.6-luna", "Luna", "0.20,1.20"))));
    assertTrue(saved.apiKeySet());
    assertEquals("…-key", saved.apiKeyHint());
    assertEquals("https://api.openai.com/v1", saved.baseUrl());
    assertEquals(1, saved.models().size());
    assertEquals("gpt-5.6-luna", saved.models().get(0).id());

    String json = service.get().toString();
    assertFalse(json.contains("sk-test-secret-key"));

    Map<String, String> env = service.envFor("openai", "gpt-5.6-luna");
    assertEquals("sk-test-secret-key", env.get("OPENAI_API_KEY"));
    assertEquals("https://api.openai.com/v1", env.get("OPENAI_BASE_URL"));
    assertEquals("0.20,1.20", env.get("HARNESS_PRICE_GPT_5_6_LUNA"));
  }

  @Test
  void omittedApiKeyKeepsStoredValue() {
    service.upsertProvider(
        "openai", new UpsertProviderRequest("OpenAI", "openai", null, "sk-keep", List.of()));
    service.upsertProvider(
        "openai", new UpsertProviderRequest("OpenAI", "openai", null, null, List.of()));
    assertTrue(service.get().providers().get(0).apiKeySet());
    assertEquals("sk-keep", service.envFor("openai", null).get("OPENAI_API_KEY"));
  }

  @Test
  void emptyApiKeyClearsStoredValue() {
    service.upsertProvider(
        "openai", new UpsertProviderRequest("OpenAI", "openai", null, "sk-gone", List.of()));
    service.upsertProvider(
        "openai", new UpsertProviderRequest("OpenAI", "openai", null, "", List.of()));
    assertFalse(service.get().providers().get(0).apiKeySet());
    assertFalse(service.envFor("openai", null).containsKey("OPENAI_API_KEY"));
  }

  @Test
  void additionalProviderRequiresBaseUrlAndUsesOpenaiAdapter() {
    ProviderView vllm = service.upsertProvider(
        "local-vllm",
        new UpsertProviderRequest(
            "Local vLLM",
            "openai",
            "http://127.0.0.1:8000/v1",
            "not-needed",
            List.of(new RegisteredModel("qwen2.5", null, "0.10,0.10"))));
    assertEquals("openai", vllm.adapter());
    assertEquals("http://127.0.0.1:8000/v1", vllm.baseUrl());
    assertEquals("openai", service.adapterName("local-vllm"));
    assertEquals(2, service.get().providers().size());

    CliException missingUrl = assertThrows(
        CliException.class,
        () -> service.upsertProvider(
            "broken", new UpsertProviderRequest("Broken", "openai", "", "k", List.of())));
    assertEquals(400, missingUrl.getHttpStatus());
  }

  @Test
  void cannotDeleteOpenai() {
    CliException e = assertThrows(CliException.class, () -> service.deleteProvider("openai"));
    assertEquals(400, e.getHttpStatus());
  }

  @Test
  void registerAndDeleteModel() {
    service.upsertModel("openai", "gpt-5.6-luna", new UpsertModelRequest("Luna", "0.2,1.2"));
    assertEquals("Luna", service.require("openai").models().get(0).label());
    service.deleteModel("openai", "gpt-5.6-luna");
    assertTrue(service.require("openai").models().isEmpty());
  }

  @Test
  void overlayReplacesModelListWhenRegistered() {
    service.upsertModel("openai", "my-model", new UpsertModelRequest(null, "1,2"));
    ObjectMapper mapper = new ObjectMapper();
    ObjectNode defaults = mapper.createObjectNode();
    defaults.putArray("providers").add("openai");
    defaults.putArray("models").add("gpt-5.6-luna");
    ObjectNode defaultRun = defaults.putObject("defaultRun");
    defaultRun.put("model", "gpt-5.6-luna");
    defaultRun.put("provider", "openai");

    service.overlayRunDefaults(defaults);

    List<String> models = new ArrayList<>();
    defaults.get("models").forEach(n -> models.add(n.asText()));
    assertTrue(models.contains("my-model"));
    assertTrue(models.contains("gpt-5.6-luna"));
    assertEquals("gpt-5.6-luna", defaults.get("defaultRun").get("model").asText());
    assertEquals("openai", defaults.get("providerProfiles").get(0).get("id").asText());
  }

  @Test
  void rejectsUnknownAdapterAndBadIds() {
    assertThrows(
        CliException.class,
        () -> service.upsertProvider(
            "x", new UpsertProviderRequest("x", "anthropic", "http://x", "k", List.of())));
    assertThrows(
        CliException.class,
        () -> service.upsertProvider(
            "Not Valid", new UpsertProviderRequest("x", "openai", "http://x", "k", List.of())));
  }

  @Test
  void secretsFileIsOwnerReadableOnlyWhenPosix() throws Exception {
    service.upsertProvider(
        "openai", new UpsertProviderRequest("OpenAI", "openai", null, "sk-posix", List.of()));
    Path file = data.resolve("secrets/providers.env");
    assertTrue(Files.isRegularFile(file));
    String text = Files.readString(file);
    assertTrue(text.contains("openai=sk-posix"));
    assertFalse(text.contains("sk-posix\nsk-posix"));
  }
}
