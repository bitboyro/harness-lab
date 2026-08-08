package ro.bitboy.harness.ui.core;

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
    String sentence = firstSentence(stderr);
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

  static String firstSentence(String text) {
    if (text == null || text.isBlank()) {
      return "";
    }
    String line = text.lines()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .filter(s -> !s.startsWith("loaded from"))
        .findFirst()
        .orElse("")
        .replaceAll("\\s+", " ");
    int cut = line.length();
    for (int i = 0; i < line.length(); i++) {
      char c = line.charAt(i);
      if (c == '.' || c == '\n') {
        cut = i + 1;
        break;
      }
    }
    if (cut > 280) {
      cut = 280;
    }
    return line.substring(0, Math.min(cut, line.length())).trim();
  }
}
