package ro.bitboy.harness.ui.dto;

import jakarta.validation.constraints.NotEmpty;
import java.util.List;

public record CompareRequest(@NotEmpty List<String> runIds) {}
