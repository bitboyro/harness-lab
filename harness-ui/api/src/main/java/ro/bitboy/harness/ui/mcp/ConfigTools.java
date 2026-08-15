package ro.bitboy.harness.ui.mcp;

import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.LlmConfig;
import ro.bitboy.harness.ui.dto.ProviderView;
import ro.bitboy.harness.ui.dto.UpsertModelRequest;
import ro.bitboy.harness.ui.dto.UpsertProviderRequest;
import ro.bitboy.harness.ui.service.ProviderCatalogService;

@Component
public class ConfigTools {

  private final ProviderCatalogService providers;

  public ConfigTools(ProviderCatalogService providers) {
    this.providers = providers;
  }

  @Tool(name = Capabilities.GET_LLM_CONFIG,
      description = "Read LLM provider profiles. API keys are never returned.")
  public LlmConfig getLlmConfig() {
    return providers.get();
  }

  @Tool(name = Capabilities.UPSERT_PROVIDER,
      description = "Create or update an LLM provider profile (OpenAI-compatible).")
  public ProviderView upsertProvider(String id, UpsertProviderRequest body) {
    return providers.upsertProvider(id, body);
  }

  @Tool(name = Capabilities.DELETE_PROVIDER,
      description = "Delete an additional LLM provider profile (not openai).")
  public void deleteProvider(String id) {
    providers.deleteProvider(id);
  }

  @Tool(name = Capabilities.UPSERT_MODEL,
      description = "Register or update a model id on a provider profile.")
  public ProviderView upsertModel(String id, String modelId, UpsertModelRequest body) {
    return providers.upsertModel(id, modelId, body);
  }

  @Tool(name = Capabilities.DELETE_MODEL,
      description = "Unregister a model id from a provider profile.")
  public ProviderView deleteModel(String id, String modelId) {
    return providers.deleteModel(id, modelId);
  }
}
