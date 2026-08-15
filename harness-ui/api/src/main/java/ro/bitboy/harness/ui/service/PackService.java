package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.core.DiskDelete;
import ro.bitboy.harness.ui.core.ExitCodeMapper;
import ro.bitboy.harness.ui.core.HarnessCli;
import ro.bitboy.harness.ui.core.ProcessResult;
import ro.bitboy.harness.ui.dto.DraftPackRequest;
import ro.bitboy.harness.ui.dto.PackDocument;
import ro.bitboy.harness.ui.dto.PackRef;
import ro.bitboy.harness.ui.dto.WritePackResponse;

@Service
public class PackService {

  private final HarnessProperties props;
  private final HarnessCli cli;
  private final TargetService targets;
  private final AdapterService adapter;

  public PackService(
      HarnessProperties props,
      HarnessCli cli,
      TargetService targets,
      AdapterService adapter) {
    this.props = props;
    this.cli = cli;
    this.targets = targets;
    this.adapter = adapter;
  }

  public PackRef draft(DraftPackRequest req) {
    String outId = (req.outId() == null || req.outId().isBlank())
        ? "pack-" + UUID.randomUUID().toString().replace("-", "").substring(0, 10)
        : req.outId();
    String source = targets.scaffoldSource(req.targetId());
    Path out = packPath(outId);
    try {
      Files.createDirectories(out.getParent());
    } catch (IOException e) {
      throw new CliException(40, "cannot create packs dir: " + e.getMessage());
    }
    List<String> args = new ArrayList<>();
    args.add("scaffold");
    args.add(source);
    args.add("-o");
    args.add(out.toString());
    args.add("--id");
    args.add(outId);
    if ("openapi".equals(targets.require(req.targetId()).kind())) {
      args.add("--no-mcp");
    }
    ProcessResult result = cli.runHarness(args);
    if (result.exitCode() != 0) {
      // Prefer Python/CLI text — do not invent a Java PackError.
      String msg = AdapterService.packErrorText(result);
      throw new CliException(result.exitCode(), msg);
    }
    JsonNode validation = softValidate(out);
    boolean valid = validation.path("valid").asBoolean(true);
    String error = validation.path("error").isNull() ? null : validation.path("error").asText(null);
    return new PackRef(outId, "packs/" + outId + ".yaml", valid, error);
  }

  public List<PackRef> list() {
    Path dir = props.packsDir();
    if (!Files.isDirectory(dir)) {
      return List.of();
    }
    List<PackRef> out = new ArrayList<>();
    try (var stream = Files.list(dir)) {
      stream
          .filter(Files::isRegularFile)
          .filter(p -> p.getFileName().toString().endsWith(".yaml"))
          .sorted()
          .forEach(p -> {
            String name = p.getFileName().toString();
            String id = name.substring(0, name.length() - ".yaml".length());
            out.add(new PackRef(id, "packs/" + name, true, null));
          });
    } catch (IOException e) {
      throw new CliException(40, "cannot list packs: " + e.getMessage());
    }
    return out;
  }

  public PackDocument read(String id) {
    Path path = requirePackFile(id);
    try {
      return new PackDocument(id, Files.readString(path, StandardCharsets.UTF_8));
    } catch (IOException e) {
      throw new CliException(40, "cannot read pack: " + e.getMessage());
    }
  }

  public WritePackResponse write(String id, String yaml) {
    Path path = packPath(id);
    try {
      Files.createDirectories(path.getParent());
      Files.writeString(path, yaml == null ? "" : yaml, StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new CliException(40, "cannot write pack: " + e.getMessage());
    }
    try {
      JsonNode node = adapter.packValidate(path.toString(), null);
      boolean valid = node.path("valid").asBoolean(false);
      String error = node.path("error").isMissingNode() || node.path("error").isNull()
          ? null
          : node.path("error").asText();
      return new WritePackResponse(id, valid, error);
    } catch (CliException e) {
      // Surface PackError text from Python.
      return new WritePackResponse(id, false, e.getMessage());
    }
  }

  public JsonNode validate(String id, String baseUrl) {
    Path path = requirePackFile(id);
    return adapter.packValidate(path.toString(), baseUrl);
  }

  public Path requirePackFile(String id) {
    Path path = packPath(id);
    if (!Files.isRegularFile(path)) {
      throw new CliException(2, 404, "unknown pack: " + id);
    }
    return path;
  }

  public Path packPath(String id) {
    if (id == null || id.isBlank() || id.contains("..") || id.contains("/") || id.contains("\\")) {
      throw new CliException(2, 400, "invalid pack id");
    }
    return props.packsDir().resolve(id + ".yaml");
  }

  public void delete(String id) {
    Path path = requirePackFile(id);
    try {
      Files.delete(path);
    } catch (IOException e) {
      throw new CliException(40, "cannot delete pack: " + e.getMessage());
    }
  }

  private JsonNode softValidate(Path path) {
    try {
      return adapter.packValidate(path.toString(), null);
    } catch (CliException e) {
      // Draft still succeeds; validity reported on PackRef.
      return propsJson(false, e.getMessage());
    }
  }

  private static JsonNode propsJson(boolean valid, String error) {
    try {
      var m = new com.fasterxml.jackson.databind.ObjectMapper();
      var n = m.createObjectNode();
      n.put("valid", valid);
      if (error != null) {
        n.put("error", error);
      } else {
        n.putNull("error");
      }
      return n;
    } catch (Exception e) {
      throw new CliException(ExitCodeMapper.CONFIG_INFRA, "json error");
    }
  }
}
