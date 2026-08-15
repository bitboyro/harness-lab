package ro.bitboy.harness.ui.mcp;

import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.CompareRequest;
import ro.bitboy.harness.ui.dto.CompareResult;
import ro.bitboy.harness.ui.service.CompareService;

@Component
public class CompareTools {

  private final CompareService compare;

  public CompareTools(CompareService compare) {
    this.compare = compare;
  }

  @Tool(name = Capabilities.COMPARE_RUNS, description = "Compare two or more runs; exit-3 refusal is a normal response.")
  public CompareResult compareRuns(CompareRequest body) {
    return compare.compare(body);
  }
}
