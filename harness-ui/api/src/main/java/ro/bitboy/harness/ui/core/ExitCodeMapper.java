package ro.bitboy.harness.ui.core;

import java.util.Locale;
import ro.bitboy.harness.ui.dto.RunJob;

/**
 * CLI exit codes → job status / HTTP treatment (contracts.md).
 */
public final class ExitCodeMapper {

  public static final int SUCCESS = 0;
  public static final int DECLINED = 1;
  public static final int ARGUMENT = 2;
  public static final int POOLING_REFUSED = 3;
  public static final int CONFIG_INFRA = 40;
  public static final int CANCELLED = 130;

  private ExitCodeMapper() {}

  public static RunJob.Status toJobStatus(int exitCode) {
    return switch (exitCode) {
      case SUCCESS -> RunJob.Status.succeeded;
      case DECLINED -> RunJob.Status.declined;
      case CANCELLED -> RunJob.Status.cancelled;
      case ARGUMENT, CONFIG_INFRA, POOLING_REFUSED -> RunJob.Status.failed;
      default -> RunJob.Status.failed;
    };
  }

  /**
   * HTTP status for a synchronous CLI failure that is not a handled special case
   * (compare refusal, dry-run projection).
   */
  public static int httpStatus(int exitCode) {
    return switch (exitCode) {
      case ARGUMENT -> 400;
      case CONFIG_INFRA -> 503;
      case DECLINED -> 409;
      case CANCELLED -> 409;
      default -> 500;
    };
  }

  /** One-sentence client message; never dumps raw env-bearing stderr. */
  public static String clientMessage(int exitCode, String stderr) {
    String sentence = bestSentence(exitCode, stderr);
    return switch (exitCode) {
      case SUCCESS -> "ok";
      case DECLINED -> sentence.isBlank() ? "declined or nothing to do" : sentence;
      case ARGUMENT -> sentence.isBlank() ? "invalid arguments" : sentence;
      case POOLING_REFUSED -> sentence.isBlank() ? "REFUSING TO POOL" : sentence;
      case CONFIG_INFRA -> sentence.isBlank() ? "configuration or infrastructure failure" : sentence;
      case CANCELLED -> "cancelled";
      default -> sentence.isBlank() ? "process failed with exit " + exitCode : sentence;
    };
  }

  static String bestSentence(int exitCode, String text) {
    if (text == null || text.isBlank()) {
      return "";
    }
    // Projection lines precede the real reason on exit 1 (disk, abort, budget).
    String signal = text.lines()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .filter(s -> !s.startsWith("loaded from"))
        .filter(ExitCodeMapper::isSignalLine)
        .findFirst()
        .orElse("");
    if (!signal.isBlank()) {
      return trimToSentence(signal);
    }
    return firstSentence(text);
  }

  static boolean isSignalLine(String line) {
    String lower = line.toLowerCase(Locale.ROOT);
    return lower.contains("not enough disk")
        || lower.startsWith("aborted")
        || lower.startsWith("refusing to start")
        || lower.startsWith("refuses budget")
        || lower.contains("nothing to do")
        || lower.startsWith("not approved")
        || lower.startsWith("interrupted");
  }

  static String firstSentence(String text) {
    if (text == null || text.isBlank()) {
      return "";
    }
    String line = text.lines()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .filter(s -> !s.startsWith("loaded from"))
        .findFirst()
        .orElse("");
    return trimToSentence(line.replaceAll("\\s+", " "));
  }

  static String trimToSentence(String line) {
    if (line == null || line.isBlank()) {
      return "";
    }
    line = line.replaceAll("\\s+", " ");
    int cut = line.length();
    // Sentence boundary: period followed by space/end — not version dots (3.13) or paths.
    for (int i = 0; i < line.length(); i++) {
      char c = line.charAt(i);
      if (c == '.' && (i + 1 >= line.length() || line.charAt(i + 1) == ' ')) {
        cut = i + 1;
        break;
      }
    }
    if (cut > 280) {
      cut = 280;
    }
    return line.substring(0, Math.min(cut, line.length())).trim();
  }

  /**
   * Map a generate {@code errors.json} object to a {@link CliException} with the
   * contract HTTP status (2 → 400, 40 → 503).
   */
  public static CliException fromGenerateError(com.fasterxml.jackson.databind.JsonNode error) {
    if (error == null || error.isNull() || error.isMissingNode()) {
      return new CliException(ARGUMENT, httpStatus(ARGUMENT), "generate failed");
    }
    int exit = error.path("exit_code").asInt(ARGUMENT);
    String message = error.path("message").asText("generate failed");
    String hint = error.path("operator_hint").asText("");
    if (hint.isBlank()) {
      hint = error.path("operator_fix").asText("");
    }
    if (!hint.isBlank()) {
      message = message + " — " + hint;
    }
    return new CliException(exit, httpStatus(exit), message);
  }

  /** Prefer structured generate error text over a raw console tail. */
  public static String messageFromGenerateError(com.fasterxml.jackson.databind.JsonNode error) {
    if (error == null || error.isNull() || error.isMissingNode()) {
      return "";
    }
    String message = error.path("message").asText("").trim();
    String hint = error.path("operator_hint").asText("");
    if (hint.isBlank()) {
      hint = error.path("operator_fix").asText("");
    }
    if (!hint.isBlank()) {
      return message.isBlank() ? hint : message + " — " + hint;
    }
    return message;
  }
}
