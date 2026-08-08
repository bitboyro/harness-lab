package ro.bitboy.harness.ui;

/**
 * Capability names are simultaneously MCP tool names and REST {@code operationId}s.
 * Frozen in {@code harness-ui/docs/contracts.md}.
 */
public final class Capabilities {
  public static final String UPLOAD_CONTRACT = "upload_contract";
  public static final String LIST_TARGETS = "list_targets";
  public static final String LINT_TARGET = "lint_target";
  public static final String DRAFT_PACK = "draft_pack";
  public static final String READ_PACK = "read_pack";
  public static final String WRITE_PACK = "write_pack";
  public static final String VALIDATE_PACK = "validate_pack";
  public static final String PROJECT_RUN_COST = "project_run_cost";
  public static final String START_RUN = "start_run";
  public static final String GET_RUN_PROGRESS = "get_run_progress";
  public static final String LIST_RUNS = "list_runs";
  public static final String GET_REPORT = "get_report";
  public static final String GET_TRANSCRIPT = "get_transcript";
  public static final String COMPARE_RUNS = "compare_runs";
  public static final String GET_BRIEF = "get_brief";
  public static final String LIST_ARTIFACTS = "list_artifacts";
  public static final String GET_ARTIFACT = "get_artifact";
  public static final String PUT_ARTIFACT = "put_artifact";

  private Capabilities() {}
}
