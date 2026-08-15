package ro.bitboy.harness.ui.web;

import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.LlmConfig;
import ro.bitboy.harness.ui.dto.ProviderView;
import ro.bitboy.harness.ui.dto.UpsertModelRequest;
import ro.bitboy.harness.ui.dto.UpsertProviderRequest;
import ro.bitboy.harness.ui.service.ConfigService;
import ro.bitboy.harness.ui.service.ProviderCatalogService;

/** UI catalog — not a spend capability; adapter-sourced defaults plus LLM profiles. */
@RestController
@RequestMapping("/api/v1/config")
public class ConfigController {

  private final ConfigService config;
  private final ProviderCatalogService providers;

  public ConfigController(ConfigService config, ProviderCatalogService providers) {
    this.config = config;
    this.providers = providers;
  }

  @GetMapping("/run-defaults")
  @Operation(operationId = "get_run_defaults")
  public JsonNode runDefaults() {
    return config.runDefaults();
  }

  @GetMapping("/llm")
  @Operation(operationId = Capabilities.GET_LLM_CONFIG)
  public LlmConfig llm() {
    return providers.get();
  }

  @PutMapping("/providers/{id}")
  @Operation(operationId = Capabilities.UPSERT_PROVIDER)
  public ProviderView upsertProvider(
      @PathVariable String id, @Valid @RequestBody UpsertProviderRequest body) {
    return providers.upsertProvider(id, body);
  }

  @DeleteMapping("/providers/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  @Operation(operationId = Capabilities.DELETE_PROVIDER)
  public void deleteProvider(@PathVariable String id) {
    providers.deleteProvider(id);
  }

  @PutMapping("/providers/{id}/models/{modelId}")
  @Operation(operationId = Capabilities.UPSERT_MODEL)
  public ProviderView upsertModel(
      @PathVariable String id,
      @PathVariable String modelId,
      @RequestBody(required = false) UpsertModelRequest body) {
    return providers.upsertModel(id, modelId, body == null ? new UpsertModelRequest(null, null) : body);
  }

  @DeleteMapping("/providers/{id}/models/{modelId}")
  @Operation(operationId = Capabilities.DELETE_MODEL)
  public ProviderView deleteModel(@PathVariable String id, @PathVariable String modelId) {
    return providers.deleteModel(id, modelId);
  }
}
