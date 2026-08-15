package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CompareResult(
    boolean refused,
    String refusalText,
    String brokenBoundary,
    String artifactDir,
    String stdout
) {}
