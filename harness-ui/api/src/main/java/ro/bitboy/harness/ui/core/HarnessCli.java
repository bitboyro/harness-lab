package ro.bitboy.harness.ui.core;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.config.HarnessProperties;

/**
 * Builds and runs {@code harness} / adapter argv lists. Exit-code mapping lives
 * in {@link ExitCodeMapper}; this class never invents judgment.
 */
@Component
public class HarnessCli {

  /** Env-ish tokens we may surface in CostProjection — never raw stderr. */
  private static final Pattern ENV_NAME = Pattern.compile(
      "\\b([A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET|_KEY|_URL))\\b");

  private final HarnessProperties props;
  private final ProcessRunner runner;

  public HarnessCli(HarnessProperties props, ProcessRunner runner) {
    this.props = props;
    this.runner = runner;
  }

  public ProcessResult runHarness(List<String> args) {
    return runHarness(args, Map.of());
  }

  public ProcessResult runHarness(List<String> args, Map<String, String> env) {
    List<String> cmd = new ArrayList<>();
    cmd.add(props.getCli());
    cmd.addAll(args);
    // Call the 3-arg form so Mockito mocks (no default-method dispatch) work.
    return runner.run(cmd, null, env == null ? Map.of() : env);
  }

  public Process startHarness(List<String> args, Path consoleLog) {
    return startHarness(args, consoleLog, Map.of());
  }

  public Process startHarness(List<String> args, Path consoleLog, Map<String, String> env) {
    List<String> cmd = new ArrayList<>();
    cmd.add(props.getCli());
    cmd.addAll(args);
    return runner.start(cmd, null, env == null ? Map.of() : env, consoleLog);
  }

  public ProcessResult runAdapter(String subcommand, List<String> args) {
    List<String> tail = new ArrayList<>();
    tail.add(subcommand);
    tail.addAll(args);
    return runAdapterArgs(tail);
  }

  public ProcessResult runAdapterArgs(List<String> adapterArgs) {
    List<String> cmd = new ArrayList<>();
    cmd.add(props.getAdapter());
    cmd.add(props.getAdapterScript().toString());
    cmd.add("--expect-version");
    cmd.add(props.getExpectVersion());
    cmd.addAll(adapterArgs);
    return runner.run(cmd, null, Map.of());
  }

  /** Extract allow-listed credential env names from stderr; never echo the rest. */
  public static List<String> extractStderrNames(String stderr) {
    if (stderr == null || stderr.isBlank()) {
      return List.of();
    }
    List<String> names = new ArrayList<>();
    Matcher m = ENV_NAME.matcher(stderr);
    while (m.find()) {
      String name = m.group(1);
      if (!names.contains(name)) {
        names.add(name);
      }
    }
    return List.copyOf(names);
  }

  public HarnessProperties props() {
    return props;
  }
}
