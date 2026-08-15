package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ExperimentRunProjection(
    String projectionText,
    int exitCode,
    List<String> stderrNames,
    int missingCells,
    int voidedCells,
    String slice,
    List<String> armsScheduled
) {}
