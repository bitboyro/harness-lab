package ro.bitboy.harness.ui.web;

import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.CompareRequest;
import ro.bitboy.harness.ui.dto.CompareResult;
import ro.bitboy.harness.ui.service.CompareService;

@RestController
@RequestMapping("/api/v1/compare")
public class CompareController {

  private final CompareService compare;

  public CompareController(CompareService compare) {
    this.compare = compare;
  }

  @PostMapping
  @Operation(operationId = Capabilities.COMPARE_RUNS)
  public CompareResult compare(@Valid @RequestBody CompareRequest body) {
    return compare.compare(body);
  }
}
