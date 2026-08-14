package ro.bitboy.harness.ui.core;

/** Mapped CLI / adapter failure surfaced to HTTP. */
public class CliException extends RuntimeException {

  private final int exitCode;
  private final int httpStatus;

  public CliException(int exitCode, String message) {
    this(exitCode, ExitCodeMapper.httpStatus(exitCode), message);
  }

  public CliException(int exitCode, int httpStatus, String message) {
    super(message);
    this.exitCode = exitCode;
    this.httpStatus = httpStatus;
  }

  public int getExitCode() {
    return exitCode;
  }

  public int getHttpStatus() {
    return httpStatus;
  }
}
