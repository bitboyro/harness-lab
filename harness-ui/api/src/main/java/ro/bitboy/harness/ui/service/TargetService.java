package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.dto.Target;

@Service
public class TargetService {

  private final HarnessProperties props;
  private final ObjectMapper mapper;

  public TargetService(HarnessProperties props) {
    this.props = props;
    this.mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
  }

  public Target upload(MultipartFile file, String mcpUrl) {
    boolean hasFile = file != null && !file.isEmpty();
    boolean hasUrl = mcpUrl != null && !mcpUrl.isBlank();
    if (hasFile == hasUrl) {
      throw new CliException(2, 400, "provide exactly one of file or mcp_url");
    }
    String id = "t-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    Path dir = props.targetsDir().resolve(id);
    try {
      Files.createDirectories(dir);
      Target target;
      if (hasFile) {
        String original = file.getOriginalFilename() != null ? file.getOriginalFilename() : "spec.json";
        String lower = original.toLowerCase(Locale.ROOT);
        Path dest = dir.resolve(lower.endsWith(".yaml") || lower.endsWith(".yml") ? "spec.yaml" : "spec.json");
        try (InputStream in = file.getInputStream()) {
          Files.copy(in, dest);
        }
        target = new Target(id, "openapi", original, Instant.now());
      } else {
        Files.writeString(dir.resolve("mcp-url.txt"), mcpUrl.trim(), StandardCharsets.UTF_8);
        target = new Target(id, "mcp", mcpUrl.trim(), Instant.now());
      }
      mapper.writerWithDefaultPrettyPrinter().writeValue(dir.resolve("meta.json").toFile(), target);
      return target;
    } catch (IOException e) {
      throw new CliException(40, "cannot store target: " + e.getMessage());
    }
  }

  public List<Target> list() {
    Path root = props.targetsDir();
    if (!Files.isDirectory(root)) {
      return List.of();
    }
    List<Target> out = new ArrayList<>();
    try (var stream = Files.list(root)) {
      stream.filter(Files::isDirectory).forEach(dir -> {
        Path meta = dir.resolve("meta.json");
        if (Files.isRegularFile(meta)) {
          try {
            out.add(mapper.readValue(meta.toFile(), Target.class));
          } catch (IOException ignored) {
            // skip corrupt
          }
        }
      });
    } catch (IOException e) {
      throw new CliException(40, "cannot list targets: " + e.getMessage());
    }
    out.sort(Comparator.comparing(Target::createdAt, Comparator.nullsLast(Comparator.naturalOrder())).reversed());
    return out;
  }

  public Target require(String id) {
    Path meta = props.targetsDir().resolve(id).resolve("meta.json");
    if (!Files.isRegularFile(meta)) {
      throw new CliException(2, 404, "unknown target: " + id);
    }
    try {
      return mapper.readValue(meta.toFile(), Target.class);
    } catch (IOException e) {
      throw new CliException(40, "unreadable target meta: " + id);
    }
  }

  public Path specOrUrlPath(String id) {
    Target t = require(id);
    Path dir = props.targetsDir().resolve(id);
    if ("mcp".equals(t.kind())) {
      return dir.resolve("mcp-url.txt");
    }
    Path json = dir.resolve("spec.json");
    if (Files.isRegularFile(json)) {
      return json;
    }
    Path yaml = dir.resolve("spec.yaml");
    if (Files.isRegularFile(yaml)) {
      return yaml;
    }
    throw new CliException(40, "target has no spec: " + id);
  }

  public String scaffoldSource(String id) {
    Target t = require(id);
    Path dir = props.targetsDir().resolve(id);
    try {
      if ("mcp".equals(t.kind())) {
        return Files.readString(dir.resolve("mcp-url.txt")).trim();
      }
      return specOrUrlPath(id).toAbsolutePath().toString();
    } catch (IOException e) {
      throw new CliException(40, "cannot read target source: " + e.getMessage());
    }
  }
}
