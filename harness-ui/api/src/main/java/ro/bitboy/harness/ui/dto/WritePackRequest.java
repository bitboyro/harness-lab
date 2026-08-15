package ro.bitboy.harness.ui.dto;

import jakarta.validation.constraints.NotNull;

public record WritePackRequest(@NotNull String yaml) {}
