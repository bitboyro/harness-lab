package ro.bitboy.harness.ui.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record StartGenerateRequest(
    @NotBlank String jobId,
    @NotBlank String targetId,
    @NotNull GenerateStaging staging,
    GeneratePhases phases,
    Boolean approveEnrich,
    /** When true, keep A/B MCP arms (requires MCP gateway for field HTTP). */
    Boolean mcpGateway,
    /**
     * When true, start local OpenAPI HTTP mock + MCP gateway and inject
     * staging base URL (no customer URL required).
     */
    Boolean useLocalMock,
    /**
     * Customer MCP gateway URL for A/B arms when not using local mock.
     * Written into generate.config.yaml as {@code mcp_url} (and pack {@code api.mcp.url}).
     * Ignored when {@code useLocalMock} is true.
     */
    String mcpUrl
) {}
