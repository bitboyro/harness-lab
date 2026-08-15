package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

/**
 * Create or replace a provider profile. {@code apiKey} is write-only:
 * omitted/null keeps the stored key, {@code ""} clears it.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record UpsertProviderRequest(
    String label,
    String adapter,
    String baseUrl,
    String apiKey,
    List<RegisteredModel> models
) {}
