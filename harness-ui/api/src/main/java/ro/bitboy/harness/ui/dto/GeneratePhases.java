package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record GeneratePhases(
    Boolean analyze,
    Boolean materials,
    Boolean fixtures,
    Boolean pack,
    Boolean enrich
) {}
