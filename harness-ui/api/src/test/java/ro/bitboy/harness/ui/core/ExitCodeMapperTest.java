package ro.bitboy.harness.ui.core;

import static org.junit.jupiter.api.Assertions.assertEquals;

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
}
