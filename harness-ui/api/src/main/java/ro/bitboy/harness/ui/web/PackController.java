package ro.bitboy.harness.ui.web;

import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.DraftPackRequest;
import ro.bitboy.harness.ui.dto.PackDocument;
import ro.bitboy.harness.ui.dto.PackRef;
import ro.bitboy.harness.ui.dto.ValidatePackRequest;
import ro.bitboy.harness.ui.dto.WritePackRequest;
import ro.bitboy.harness.ui.dto.WritePackResponse;
import ro.bitboy.harness.ui.service.PackService;

@RestController
@RequestMapping("/api/v1/packs")
public class PackController {

  private final PackService packs;

  public PackController(PackService packs) {
    this.packs = packs;
  }

  @GetMapping
  @Operation(operationId = Capabilities.LIST_PACKS)
  public java.util.List<PackRef> list() {
    return packs.list();
  }

  @PostMapping("/draft")
  @ResponseStatus(HttpStatus.CREATED)
  @Operation(operationId = Capabilities.DRAFT_PACK)
  public PackRef draft(@Valid @RequestBody DraftPackRequest body) {
    return packs.draft(body);
  }

  @GetMapping("/{id}")
  @Operation(operationId = Capabilities.READ_PACK)
  public PackDocument read(@PathVariable String id) {
    return packs.read(id);
  }

  @PutMapping("/{id}")
  @Operation(operationId = Capabilities.WRITE_PACK)
  public WritePackResponse write(@PathVariable String id, @Valid @RequestBody WritePackRequest body) {
    return packs.write(id, body.yaml());
  }

  @PostMapping("/{id}/validate")
  @Operation(operationId = Capabilities.VALIDATE_PACK)
  public JsonNode validate(
      @PathVariable String id,
      @RequestBody(required = false) ValidatePackRequest body) {
    String baseUrl = body == null ? null : body.baseUrl();
    return packs.validate(id, baseUrl);
  }

  @DeleteMapping("/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  @Operation(operationId = Capabilities.DELETE_PACK)
  public void delete(@PathVariable String id) {
    packs.delete(id);
  }
}
