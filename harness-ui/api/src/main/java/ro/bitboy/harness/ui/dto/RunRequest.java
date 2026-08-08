package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record RunRequest(
    @NotBlank String id,
    String packId,
    String targetId,
    List<String> presets,
    String model,
    String provider,
    String reasoningEffort,
    Integer repeats,
    boolean smoke,
    boolean probe,
    boolean resume,
    boolean dryRun,
    boolean allowCodeSandbox,
    Boolean approve
) {
  public RunRequest {
    if (presets == null) {
      presets = List.of();
    }
    if (provider == null || provider.isBlank()) {
      provider = "openai";
    }
    if (repeats == null || repeats < 1) {
      repeats = 1;
    }
  }
}
