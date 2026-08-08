package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record WritePackResponse(String id, boolean valid, String error) {}
