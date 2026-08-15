package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record UpsertModelRequest(String label, String price) {}
