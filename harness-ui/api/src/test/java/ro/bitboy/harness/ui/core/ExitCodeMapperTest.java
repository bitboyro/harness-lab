package ro.bitboy.harness.ui.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import ro.bitboy.harness.ui.dto.RunJob;

class ExitCodeMapperTest {

  @Test
  void mapsAllSixContractCodes() {
    assertEquals(RunJob.Status.succeeded, ExitCodeMapper.toJobStatus(0));
    assertEquals(RunJob.Status.declined, ExitCodeMapper.toJobStatus(1));
    assertEquals(RunJob.Status.failed, ExitCodeMapper.toJobStatus(2));
    assertEquals(RunJob.Status.failed, ExitCodeMapper.toJobStatus(3));
    assertEquals(RunJob.Status.failed, ExitCodeMapper.toJobStatus(40));
    assertEquals(RunJob.Status.cancelled, ExitCodeMapper.toJobStatus(130));
  }

  @Test
  void httpStatusForSynchronousFailures() {
    assertEquals(400, ExitCodeMapper.httpStatus(2));
    assertEquals(503, ExitCodeMapper.httpStatus(40));
    assertEquals(409, ExitCodeMapper.httpStatus(1));
    assertEquals(409, ExitCodeMapper.httpStatus(130));
  }

  @Test
  void cancelledIsNotFailed() {
    assertEquals(RunJob.Status.cancelled, ExitCodeMapper.toJobStatus(130));
    assertEquals(false, ExitCodeMapper.toJobStatus(130) == RunJob.Status.failed);
  }

  @Test
  void declinedPrefersDiskLineOverProjection() {
    String console =
        """
        loaded from .env: OPENAI_API_KEY
        0 runs — 3 arms x 4 tasks x 1 repeats. Rough projection $0.00

        not enough disk: 0 runs need ~0.0 GB of traces, 1.1 GB free (plus 5 GB reserved so the machine can still swap).
        Free space or move --out to another volume, then re-run with --resume.
        """;
    assertEquals(
        "not enough disk: 0 runs need ~0.",
        ExitCodeMapper.clientMessage(ExitCodeMapper.DECLINED, console).substring(0, 32));
  }

  @Test
  void argumentErrorKeepsPythonPathPastVersionDots() {
    String stderr =
        "/opt/homebrew/Cellar/python@3.13/3.13.2/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python: can't open file '/app/adapter/harness_json.py': [Errno 2] No such file or directory";
    String msg = ExitCodeMapper.clientMessage(ExitCodeMapper.ARGUMENT, stderr);
    assertTrue(msg.contains("can't open file"), msg);
    assertTrue(msg.contains("harness_json.py"), msg);
  }

  @Test
  void fromGenerateErrorMapsHttpStatus() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    var validation = mapper.readTree(
        "{\"exit_code\":2,\"kind\":\"validation\",\"message\":\"only 3 graded\",\"operator_hint\":\"lower min\"}");
    CliException bad = ExitCodeMapper.fromGenerateError(validation);
    assertEquals(2, bad.getExitCode());
    assertEquals(400, bad.getHttpStatus());
    assertTrue(bad.getMessage().contains("only 3 graded"));
    assertTrue(bad.getMessage().contains("lower min"));

    var infra = mapper.readTree(
        "{\"exit_code\":40,\"kind\":\"infra\",\"message\":\"disk full\",\"operator_fix\":\"free space\"}");
    CliException out = ExitCodeMapper.fromGenerateError(infra);
    assertEquals(40, out.getExitCode());
    assertEquals(503, out.getHttpStatus());
    assertTrue(out.getMessage().contains("free space"));
  }
}
