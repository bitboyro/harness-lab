package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * A model id the UI may pick for runs. {@code price} is the harness override
 * {@code HARNESS_PRICE_*} card ({@code in,out} / 4-tuple / 8-tuple).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
@JsonInclude(JsonInclude.Include.NON_NULL)
public record RegisteredModel(String id, String label, String price) {}
