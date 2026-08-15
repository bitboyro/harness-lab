package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.databind.JsonNode;

public record ProgressEnvelope(RunJob job, JsonNode progress, boolean terminal) {}
