package ro.bitboy.harness.ui.dto;

import jakarta.validation.constraints.NotBlank;

public record DraftPackRequest(@NotBlank String targetId, String outId) {}
