package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CreateExperimentRequest(
    @NotBlank String id,
    String yaml,
    String planPath
) {}
