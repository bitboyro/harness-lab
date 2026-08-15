package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ExperimentRunRequest(
    String slice,
    Boolean approve,
    Boolean allowCodeSandbox,
    Integer concurrency
) {}
