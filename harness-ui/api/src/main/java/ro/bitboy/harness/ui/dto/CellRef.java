package ro.bitboy.harness.ui.dto;

/** One matrix cell from results.jsonl — enough to fetch its transcript. */
public record CellRef(
    String arm,
    String taskId,
    int repeat,
    String outcome,
    int turns,
    int calls) {}
