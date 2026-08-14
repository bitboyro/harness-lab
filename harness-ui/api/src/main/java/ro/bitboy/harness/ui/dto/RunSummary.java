package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record RunSummary(
    String id,
    String status,
    String outDir,
    Instant startedAt,
    Instant finishedAt,
    Long ledgerRows
) {}
