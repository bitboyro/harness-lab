package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

/**
 * LLM provider profile as returned to the UI. API keys never appear here —
 * only whether a stored key exists and a short hint.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ProviderView(
    String id,
    String label,
    String adapter,
    String baseUrl,
    boolean builtin,
    boolean apiKeySet,
    String apiKeyHint,
    boolean processEnvKeySet,
    String processBaseUrl,
    List<RegisteredModel> models
) {}
