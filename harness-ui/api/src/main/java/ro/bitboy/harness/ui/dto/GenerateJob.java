package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record GenerateJob(
    String jobId,
    String status,
    String workspace
) {}
