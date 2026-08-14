package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record GenerateStaging(
    String baseUrlEnv,
    String authEnv,
    Integer seed,
    /** Optional staging base URL value — stored under /data/secrets/, not in config YAML. */
    String baseUrl,
    /** Optional auth token value — stored under /data/secrets/, not in config YAML. */
    String authToken
) {}
