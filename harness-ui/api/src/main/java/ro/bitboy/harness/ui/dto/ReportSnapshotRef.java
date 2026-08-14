package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ReportSnapshotRef(
    String at,
    String status,
    String path,
    int ledgerRows
) {}
