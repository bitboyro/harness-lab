package ro.bitboy.harness.ui.dto;

import jakarta.validation.constraints.NotEmpty;
import java.util.List;

public record AddExperimentArmsRequest(@NotEmpty List<String> presets) {}
