package ro.bitboy.harness.ui.dto;

import jakarta.validation.constraints.NotBlank;

public record UpdateExperimentRequest(@NotBlank String yaml) {}
