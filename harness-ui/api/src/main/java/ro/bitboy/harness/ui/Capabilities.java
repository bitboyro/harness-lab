package ro.bitboy.harness.ui;

/**
 * Capability names are simultaneously MCP tool names and REST {@code operationId}s.
 * Frozen in {@code harness-ui/docs/contracts.md}.
 */
public final class Capabilities {
  public static final String UPLOAD_CONTRACT = "upload_contract";
  public static final String LIST_TARGETS = "list_targets";
  public static final String GET_TARGET = "get_target";
  public static final String READ_TARGET_CONTRACT = "read_target_contract";
  public static final String WRITE_TARGET_CONTRACT = "write_target_contract";
  public static final String LINT_TARGET = "lint_target";
  public static final String DRAFT_PACK = "draft_pack";
  public static final String LIST_PACKS = "list_packs";
  public static final String READ_PACK = "read_pack";
  public static final String WRITE_PACK = "write_pack";
  public static final String VALIDATE_PACK = "validate_pack";
  public static final String PROJECT_RUN_COST = "project_run_cost";
  public static final String START_RUN = "start_run";
  public static final String GET_RUN_PROGRESS = "get_run_progress";
  public static final String LIST_RUNS = "list_runs";
  public static final String GET_REPORT = "get_report";
  public static final String GET_ANALYSIS = "get_analysis";
  public static final String GET_TRANSCRIPT = "get_transcript";
  public static final String COMPARE_RUNS = "compare_runs";
  public static final String GET_BRIEF = "get_brief";
  public static final String LIST_ARTIFACTS = "list_artifacts";
  public static final String GET_ARTIFACT = "get_artifact";
  public static final String PUT_ARTIFACT = "put_artifact";
  public static final String CREATE_EXPERIMENT = "create_experiment";
  public static final String LIST_EXPERIMENTS = "list_experiments";
  public static final String GET_EXPERIMENT = "get_experiment";
  public static final String UPDATE_EXPERIMENT = "update_experiment";
  public static final String ADD_EXPERIMENT_ARMS = "add_experiment_arms";
  public static final String PROJECT_EXPERIMENT_RUN = "project_experiment_run";
  public static final String START_EXPERIMENT_RUN = "start_experiment_run";
  public static final String GET_EXPERIMENT_COVERAGE = "get_experiment_coverage";
  public static final String LIST_EXPERIMENT_REPORTS = "list_experiment_reports";
  public static final String SNAPSHOT_EXPERIMENT_REPORT = "snapshot_experiment_report";
  public static final String START_GENERATE = "start_generate";
  public static final String GET_GENERATE_PROGRESS = "get_generate_progress";
  public static final String GET_GENERATE_MANIFEST = "get_generate_manifest";
  public static final String LIST_GENERATE_ARTIFACTS = "list_generate_artifacts";
  public static final String GET_GENERATE_ARTIFACT = "get_generate_artifact";
  public static final String CREATE_EXPERIMENT_FROM_GENERATE = "create_experiment_from_generate";
  public static final String DELETE_RUN = "delete_run";
  public static final String DELETE_PACK = "delete_pack";
  public static final String DELETE_TARGET = "delete_target";
  public static final String DELETE_EXPERIMENT = "delete_experiment";
  public static final String GET_LLM_CONFIG = "get_llm_config";
  public static final String UPSERT_PROVIDER = "upsert_provider";
  public static final String DELETE_PROVIDER = "delete_provider";
  public static final String UPSERT_MODEL = "upsert_model";
  public static final String DELETE_MODEL = "delete_model";

  private Capabilities() {}
}
