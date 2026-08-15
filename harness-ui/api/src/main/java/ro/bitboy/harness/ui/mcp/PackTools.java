package ro.bitboy.harness.ui.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Component;
import ro.bitboy.harness.ui.Capabilities;
import ro.bitboy.harness.ui.dto.DraftPackRequest;
import ro.bitboy.harness.ui.dto.PackDocument;
import ro.bitboy.harness.ui.dto.PackRef;
import ro.bitboy.harness.ui.dto.ValidatePackRequest;
import ro.bitboy.harness.ui.dto.WritePackRequest;
import ro.bitboy.harness.ui.dto.WritePackResponse;
import ro.bitboy.harness.ui.service.PackService;

@Component
public class PackTools {

  private final PackService packs;

  public PackTools(PackService packs) {
    this.packs = packs;
  }

  @Tool(name = Capabilities.LIST_PACKS, description = "List task packs on disk.")
  public java.util.List<PackRef> listPacks() {
    return packs.list();
  }

  @Tool(name = Capabilities.DRAFT_PACK, description = "Scaffold a task pack from a target.")
  public PackRef draftPack(DraftPackRequest body) {
    return packs.draft(body);
  }

  @Tool(name = Capabilities.READ_PACK, description = "Read raw pack YAML.")
  public PackDocument readPack(String id) {
    return packs.read(id);
  }

  @Tool(name = Capabilities.WRITE_PACK, description = "Write pack YAML with adapter validation.")
  public WritePackResponse writePack(String id, WritePackRequest body) {
    return packs.write(id, body.yaml());
  }

  @Tool(name = Capabilities.VALIDATE_PACK, description = "Validate a pack via the adapter.")
  public JsonNode validatePack(String id, ValidatePackRequest body) {
    String baseUrl = body == null ? null : body.baseUrl();
    return packs.validate(id, baseUrl);
  }

  @Tool(name = Capabilities.DELETE_PACK, description = "Delete a task pack YAML file.")
  public void deletePack(String id) {
    packs.delete(id);
  }
}
