package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ExperimentSummary(
    /** Results directory name — the key for GET /experiments/{id}. */
    String id,
    String status,
    boolean hasLedger,
    Double coverageFraction,
    String model,
    Instant updatedAt,
    /** Declared plan/sidecar id when it differs from the directory name. */
    String planId
) {}
