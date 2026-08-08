package ro.bitboy.harness.ui.dto;

import java.util.List;

public record CostProjection(String projectionText, int exitCode, List<String> stderrNames) {}
