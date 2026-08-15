package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ExperimentRef(
    String id,
    String path,
    String status,
    String error
) {}
