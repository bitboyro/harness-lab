package ro.bitboy.harness.ui.dto;

import java.util.List;

/** Catalog of LLM adapters the engine knows, plus named UI profiles. */
public record LlmConfig(
    List<String> adapters,
    String adaptersNote,
    List<ProviderView> providers
) {}
