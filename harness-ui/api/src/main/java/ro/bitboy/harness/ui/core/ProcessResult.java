package ro.bitboy.harness.ui.core;

/** Captured outcome of one subprocess. */
public record ProcessResult(int exitCode, String stdout, String stderr) {

  public String combinedOutput() {
    if (stdout == null || stdout.isBlank()) {
      return stderr == null ? "" : stderr;
    }
    if (stderr == null || stderr.isBlank()) {
      return stdout;
    }
    return stdout + "\n" + stderr;
  }
}
