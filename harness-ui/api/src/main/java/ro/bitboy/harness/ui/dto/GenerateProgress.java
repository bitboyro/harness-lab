package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record GenerateProgress(
    GenerateJob job,
    boolean terminal,
    JsonNode status,
    JsonNode error
) {}
