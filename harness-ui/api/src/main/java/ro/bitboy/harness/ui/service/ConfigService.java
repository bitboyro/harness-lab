package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.stereotype.Service;

@Service
public class ConfigService {

  private final AdapterService adapter;
  private final ProviderCatalogService providers;
  private final ObjectMapper mapper;

  public ConfigService(
      AdapterService adapter, ProviderCatalogService providers, ObjectMapper mapper) {
    this.adapter = adapter;
    this.providers = providers;
    this.mapper = mapper;
  }

  public JsonNode runDefaults() {
    JsonNode raw = adapter.runConfig();
    ObjectNode out = raw != null && raw.isObject()
        ? (ObjectNode) raw.deepCopy()
        : mapper.createObjectNode();
    providers.overlayRunDefaults(out);
    return out;
  }
}
