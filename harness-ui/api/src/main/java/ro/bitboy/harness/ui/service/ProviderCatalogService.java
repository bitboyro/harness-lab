package ro.bitboy.harness.ui.service;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;
import ro.bitboy.harness.ui.config.HarnessProperties;
import ro.bitboy.harness.ui.core.CliException;
import ro.bitboy.harness.ui.dto.LlmConfig;
import ro.bitboy.harness.ui.dto.ProviderView;
import ro.bitboy.harness.ui.dto.RegisteredModel;
import ro.bitboy.harness.ui.dto.UpsertModelRequest;
import ro.bitboy.harness.ui.dto.UpsertProviderRequest;

/**
 * Named LLM profiles for the UI. The engine adapter is still {@code openai};
 * extra profiles are OpenAI-compatible endpoints with their own key and URL.
 *
 * <p>Non-secret catalog: {@code /data/config/providers.json}. Keys:
 * {@code /data/secrets/providers.env} — never returned, never logged.
 */
@Service
public class ProviderCatalogService {

  public static final String OPENAI = "openai";
  public static final String ADAPTERS_NOTE =
      "The engine adapter is openai (or any OpenAI-compatible server via base URL). "
          + "Additional providers are named profiles that still use that adapter.";

  private static final Pattern PROVIDER_ID = Pattern.compile("^[a-z][a-z0-9-]{0,40}$");
  private static final Pattern MODEL_ID = Pattern.compile("^[A-Za-z0-9._:-]{1,128}$");
  private static final List<String> ENGINE_ADAPTERS = List.of(OPENAI);

  private final HarnessProperties props;
  private final ObjectMapper mapper;

  public ProviderCatalogService(HarnessProperties props, ObjectMapper mapper) {
    this.props = props;
    this.mapper = mapper;
  }

  public LlmConfig get() {
    return new LlmConfig(ENGINE_ADAPTERS, ADAPTERS_NOTE, views(loadStored()));
  }

  public ProviderView require(String id) {
    String key = normalizeId(id, "provider id");
    for (ProviderView v : views(loadStored())) {
      if (v.id().equals(key)) {
        return v;
      }
    }
    throw new CliException(2, 404, "unknown provider: " + key);
  }

  public ProviderView upsertProvider(String id, UpsertProviderRequest req) {
    if (req == null) {
      throw new CliException(2, 400, "body required");
    }
    String key = normalizeId(id, "provider id");
    String adapter = req.adapter() == null || req.adapter().isBlank()
        ? OPENAI
        : req.adapter().trim().toLowerCase(Locale.ROOT);
    if (!ENGINE_ADAPTERS.contains(adapter)) {
      throw new CliException(
          2, 400,
          "unknown adapter " + adapter + "; engine adapters: " + String.join(", ", ENGINE_ADAPTERS));
    }
    synchronized (this) {
      StoredCatalog catalog = loadStored();
      List<StoredProvider> next = new ArrayList<>();
      StoredProvider existing = null;
      for (StoredProvider p : catalog.providers()) {
        if (p.id().equals(key)) {
          existing = p;
        } else {
          next.add(p);
        }
      }
      String label = blankToNull(req.label());
      if (label == null) {
        label = existing != null ? existing.label() : key;
      }
      String baseUrl = req.baseUrl() == null
          ? (existing == null ? null : existing.baseUrl())
          : blankToNull(req.baseUrl());
      if (!OPENAI.equals(key) && baseUrl == null) {
        throw new CliException(2, 400, "baseUrl is required for additional providers");
      }
      List<RegisteredModel> models;
      if (req.models() == null) {
        models = existing == null ? List.of() : existing.models();
      } else {
        models = normalizeModels(req.models());
      }
      StoredProvider saved = new StoredProvider(key, label, adapter, baseUrl, models);
      if (OPENAI.equals(key)) {
        next.add(0, saved);
      } else {
        next.add(saved);
      }
      persistCatalog(new StoredCatalog(next));
      if (req.apiKey() != null) {
        writeSecret(key, req.apiKey());
      }
      return viewOf(saved);
    }
  }

  public void deleteProvider(String id) {
    String key = normalizeId(id, "provider id");
    if (OPENAI.equals(key)) {
      throw new CliException(2, 400, "cannot delete the built-in openai provider");
    }
    synchronized (this) {
      StoredCatalog catalog = loadStored();
      List<StoredProvider> next = new ArrayList<>();
      boolean found = false;
      for (StoredProvider p : catalog.providers()) {
        if (p.id().equals(key)) {
          found = true;
          continue;
        }
        next.add(p);
      }
      if (!found) {
        throw new CliException(2, 404, "unknown provider: " + key);
      }
      persistCatalog(new StoredCatalog(next));
      writeSecret(key, "");
    }
  }

  public ProviderView upsertModel(String providerId, String modelId, UpsertModelRequest req) {
    String pid = normalizeId(providerId, "provider id");
    String mid = normalizeModelId(modelId);
    String label = req == null ? null : blankToNull(req.label());
    String price = req == null ? null : blankToNull(req.price());
    validatePrice(price);
    synchronized (this) {
      StoredCatalog catalog = loadStored();
      List<StoredProvider> next = new ArrayList<>();
      StoredProvider updated = null;
      for (StoredProvider p : catalog.providers()) {
        if (!p.id().equals(pid)) {
          next.add(p);
          continue;
        }
        List<RegisteredModel> models = new ArrayList<>();
        boolean replaced = false;
        for (RegisteredModel m : p.models()) {
          if (m.id().equals(mid)) {
            String nextLabel = (req == null || req.label() == null)
                ? nvl(m.label(), mid)
                : (blankToNull(req.label()) == null ? mid : req.label().trim());
            String nextPrice = (req == null || req.price() == null) ? m.price() : price;
            models.add(new RegisteredModel(mid, nextLabel, nextPrice));
            replaced = true;
          } else {
            models.add(m);
          }
        }
        if (!replaced) {
          models.add(new RegisteredModel(mid, label != null ? label : mid, price));
        }
        updated = new StoredProvider(p.id(), p.label(), p.adapter(), p.baseUrl(), List.copyOf(models));
        next.add(updated);
      }
      if (updated == null) {
        throw new CliException(2, 404, "unknown provider: " + pid);
      }
      persistCatalog(new StoredCatalog(next));
      return viewOf(updated);
    }
  }

  public ProviderView deleteModel(String providerId, String modelId) {
    String pid = normalizeId(providerId, "provider id");
    String mid = normalizeModelId(modelId);
    synchronized (this) {
      StoredCatalog catalog = loadStored();
      List<StoredProvider> next = new ArrayList<>();
      StoredProvider updated = null;
      boolean found = false;
      for (StoredProvider p : catalog.providers()) {
        if (!p.id().equals(pid)) {
          next.add(p);
          continue;
        }
        List<RegisteredModel> models = new ArrayList<>();
        for (RegisteredModel m : p.models()) {
          if (m.id().equals(mid)) {
            found = true;
            continue;
          }
          models.add(m);
        }
        updated = new StoredProvider(p.id(), p.label(), p.adapter(), p.baseUrl(), List.copyOf(models));
        next.add(updated);
      }
      if (updated == null) {
        throw new CliException(2, 404, "unknown provider: " + pid);
      }
      if (!found) {
        throw new CliException(2, 404, "unknown model: " + mid);
      }
      persistCatalog(new StoredCatalog(next));
      return viewOf(updated);
    }
  }

  /**
   * Env to inject into a harness subprocess for this profile. Empty map means
   * inherit the server process environment unchanged.
   */
  public Map<String, String> envFor(String providerId, String modelId) {
    StoredProvider profile = findStored(providerId);
    Map<String, String> env = new LinkedHashMap<>();
    if (OPENAI.equals(profile.adapter())) {
      String key = readSecret(profile.id());
      if (key != null && !key.isBlank()) {
        env.put("OPENAI_API_KEY", key);
      }
      if (profile.baseUrl() != null) {
        env.put("OPENAI_BASE_URL", profile.baseUrl());
      }
    }
    if (modelId != null && !modelId.isBlank()) {
      for (RegisteredModel m : profile.models()) {
        if (modelId.equals(m.id()) && m.price() != null && !m.price().isBlank()) {
          env.put(priceEnvKey(m.id()), m.price().trim());
          break;
        }
      }
    }
    return Map.copyOf(env);
  }

  /** Resolve env from an experiment sidecar's {@code llm_provider} + model. */
  public Map<String, String> envForExperiment(String llmProvider, String model) {
    String pid = (llmProvider == null || llmProvider.isBlank()) ? OPENAI : llmProvider.trim();
    try {
      return envFor(pid, model);
    } catch (CliException e) {
      if (e.getHttpStatus() == 404) {
        return envFor(OPENAI, model);
      }
      throw e;
    }
  }

  /** Adapter name the engine {@code --provider} flag accepts. */
  public String adapterName(String providerId) {
    if (providerId == null || providerId.isBlank()) {
      return OPENAI;
    }
    try {
      return findStored(providerId).adapter();
    } catch (CliException e) {
      if (e.getHttpStatus() == 404) {
        return providerId.trim();
      }
      throw e;
    }
  }

  public void overlayRunDefaults(ObjectNode out) {
    if (out == null) {
      return;
    }
    List<ProviderView> profiles = views(loadStored());
    ArrayNode providerIds = out.putArray("providers");
    ArrayNode profileArr = out.putArray("providerProfiles");
    List<String> openaiModels = new ArrayList<>();
    for (ProviderView p : profiles) {
      providerIds.add(p.id());
      ObjectNode node = profileArr.addObject();
      node.put("id", p.id());
      node.put("label", p.label());
      node.put("adapter", p.adapter());
      ArrayNode models = node.putArray("models");
      for (RegisteredModel m : p.models()) {
        ObjectNode mn = models.addObject();
        mn.put("id", m.id());
        if (m.label() != null) {
          mn.put("label", m.label());
        }
        if (OPENAI.equals(p.id())) {
          openaiModels.add(m.id());
        }
      }
    }
    if (!openaiModels.isEmpty()) {
      ArrayNode models = out.putArray("models");
      openaiModels.forEach(models::add);
      ObjectNode defaultRun = out.has("defaultRun") && out.get("defaultRun").isObject()
          ? (ObjectNode) out.get("defaultRun")
          : out.putObject("defaultRun");
      defaultRun.put("provider", OPENAI);
      String current = defaultRun.path("model").asText("");
      if (!openaiModels.contains(current)) {
        defaultRun.put("model", openaiModels.get(0));
      }
      JsonNode templates = out.get("experimentTemplates");
      if (templates != null && templates.isArray()) {
        for (JsonNode t : templates) {
          if (!t.isObject()) {
            continue;
          }
          JsonNode defaultsNode = t.get("defaults");
          if (defaultsNode == null || !defaultsNode.isObject()) {
            continue;
          }
          ObjectNode defaults = (ObjectNode) defaultsNode;
          defaults.put("provider", OPENAI);
          String tm = defaults.path("model").asText("");
          if (!openaiModels.contains(tm)) {
            defaults.put("model", openaiModels.get(0));
          }
        }
      }
    }
  }

  private StoredProvider findStored(String providerId) {
    String key = normalizeId(providerId == null || providerId.isBlank() ? OPENAI : providerId, "provider id");
    synchronized (this) {
      for (StoredProvider p : loadStored().providers()) {
        if (p.id().equals(key)) {
          return p;
        }
      }
    }
    throw new CliException(2, 404, "unknown provider: " + key);
  }

  private List<ProviderView> views(StoredCatalog catalog) {
    List<ProviderView> out = new ArrayList<>();
    for (StoredProvider p : catalog.providers()) {
      out.add(viewOf(p));
    }
    return List.copyOf(out);
  }

  private ProviderView viewOf(StoredProvider p) {
    String secret = readSecret(p.id());
    boolean stored = secret != null && !secret.isBlank();
    boolean processKey = OPENAI.equals(p.id())
        && (notBlank(System.getenv("OPENAI_API_KEY")) || notBlank(peekDotEnv("OPENAI_API_KEY")));
    String processUrl = OPENAI.equals(p.id())
        ? firstNonBlank(System.getenv("OPENAI_BASE_URL"), peekDotEnv("OPENAI_BASE_URL"))
        : null;
    return new ProviderView(
        p.id(),
        p.label(),
        p.adapter(),
        p.baseUrl(),
        OPENAI.equals(p.id()),
        stored,
        stored ? hint(secret) : null,
        processKey,
        processUrl,
        p.models());
  }

  private StoredCatalog loadStored() {
    Path file = catalogFile();
    StoredCatalog catalog;
    if (!Files.isRegularFile(file)) {
      catalog = new StoredCatalog(List.of());
    } else {
      try {
        catalog = mapper.readValue(Files.readString(file, StandardCharsets.UTF_8), StoredCatalog.class);
      } catch (IOException e) {
        throw new CliException(40, "cannot read provider catalog: " + e.getMessage());
      }
      if (catalog == null || catalog.providers() == null) {
        catalog = new StoredCatalog(List.of());
      }
    }
    List<StoredProvider> providers = new ArrayList<>();
    boolean hasOpenai = false;
    for (StoredProvider p : catalog.providers()) {
      if (p == null || p.id() == null || p.id().isBlank()) {
        continue;
      }
      List<RegisteredModel> models = p.models() == null ? List.of() : normalizeModels(p.models());
      String adapter = p.adapter() == null || p.adapter().isBlank() ? OPENAI : p.adapter();
      StoredProvider clean = new StoredProvider(
          p.id(),
          p.label() == null || p.label().isBlank() ? p.id() : p.label(),
          adapter,
          blankToNull(p.baseUrl()),
          models);
      if (OPENAI.equals(clean.id())) {
        hasOpenai = true;
        providers.add(0, clean);
      } else {
        providers.add(clean);
      }
    }
    if (!hasOpenai) {
      providers.add(0, defaultOpenai());
    }
    return new StoredCatalog(List.copyOf(providers));
  }

  private void persistCatalog(StoredCatalog catalog) {
    try {
      Path dir = props.configDir();
      Files.createDirectories(dir);
      Path file = catalogFile();
      String json = mapper.writerWithDefaultPrettyPrinter().writeValueAsString(catalog) + "\n";
      Files.writeString(file, json, StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new CliException(40, "cannot write provider catalog: " + e.getMessage());
    }
  }

  private Path catalogFile() {
    return props.configDir().resolve("providers.json");
  }

  private Path secretsFile() {
    return props.secretsDir().resolve("providers.env");
  }

  private Map<String, String> loadSecrets() {
    Path file = secretsFile();
    if (!Files.isRegularFile(file)) {
      return Map.of();
    }
    try {
      Map<String, String> out = new LinkedHashMap<>();
      for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
        String trimmed = line.trim();
        if (trimmed.isEmpty() || trimmed.startsWith("#")) {
          continue;
        }
        int eq = trimmed.indexOf('=');
        if (eq <= 0) {
          continue;
        }
        out.put(trimmed.substring(0, eq).trim(), trimmed.substring(eq + 1));
      }
      return out;
    } catch (IOException e) {
      throw new CliException(40, "cannot read provider secrets: " + e.getMessage());
    }
  }

  private String readSecret(String providerId) {
    return loadSecrets().get(providerId);
  }

  private void writeSecret(String providerId, String value) {
    try {
      Path dir = props.secretsDir();
      Files.createDirectories(dir);
      Map<String, String> secrets = new LinkedHashMap<>(loadSecrets());
      if (value == null || value.isBlank()) {
        secrets.remove(providerId);
      } else {
        if (value.contains("\n") || value.contains("\r")) {
          throw new CliException(2, 400, "api key must be a single line");
        }
        secrets.put(providerId, value);
      }
      Path file = secretsFile();
      if (secrets.isEmpty()) {
        Files.deleteIfExists(file);
        return;
      }
      StringBuilder sb = new StringBuilder();
      sb.append("# LLM provider API keys — do not commit\n");
      for (Map.Entry<String, String> e : secrets.entrySet()) {
        sb.append(e.getKey()).append('=').append(e.getValue()).append('\n');
      }
      Files.writeString(file, sb.toString(), StandardCharsets.UTF_8);
      try {
        Set<PosixFilePermission> perms = EnumSet.of(
            PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE);
        Files.setPosixFilePermissions(file, perms);
      } catch (UnsupportedOperationException ignored) {
        // non-POSIX volumes
      }
    } catch (CliException e) {
      throw e;
    } catch (IOException e) {
      throw new CliException(40, "cannot write provider secrets: " + e.getMessage());
    }
  }

  private static StoredProvider defaultOpenai() {
    return new StoredProvider(
        OPENAI,
        "OpenAI",
        OPENAI,
        null,
        List.of(new RegisteredModel("gpt-5.6-luna", "gpt-5.6-luna", null)));
  }

  /**
   * Presence-only peek of a name in the nearest {@code .env} (same walk as the
   * harness CLI). Never returns the value to callers that would log or serialize it.
   */
  private String peekDotEnv(String name) {
    Path found = findDotEnv();
    if (found == null) {
      return null;
    }
    try {
      for (String raw : Files.readAllLines(found, StandardCharsets.UTF_8)) {
        String line = raw.trim();
        if (line.isEmpty() || line.startsWith("#") || !line.contains("=")) {
          continue;
        }
        int eq = line.indexOf('=');
        String key = line.substring(0, eq).trim();
        if (key.startsWith("export ")) {
          key = key.substring("export ".length()).trim();
        }
        if (!name.equals(key)) {
          continue;
        }
        String value = line.substring(eq + 1).trim();
        if (value.length() >= 2
            && (value.charAt(0) == '"' || value.charAt(0) == '\'')
            && value.charAt(0) == value.charAt(value.length() - 1)) {
          value = value.substring(1, value.length() - 1);
        }
        return blankToNull(value);
      }
    } catch (IOException ignored) {
      return null;
    }
    return null;
  }

  private Path findDotEnv() {
    List<Path> starts = new ArrayList<>();
    starts.add(Path.of("").toAbsolutePath());
    if (props.getData() != null) {
      starts.add(props.getData().toAbsolutePath());
    }
    for (Path start : starts) {
      Path dir = start;
      for (int i = 0; i < 8 && dir != null; i++) {
        Path candidate = dir.resolve(".env");
        if (Files.isRegularFile(candidate)) {
          return candidate;
        }
        if (Files.exists(dir.resolve(".git"))) {
          break;
        }
        dir = dir.getParent();
      }
    }
    return null;
  }

  private static List<RegisteredModel> normalizeModels(List<RegisteredModel> raw) {
    List<RegisteredModel> out = new ArrayList<>();
    for (RegisteredModel m : raw) {
      if (m == null || m.id() == null || m.id().isBlank()) {
        continue;
      }
      String id = normalizeModelId(m.id());
      String price = blankToNull(m.price());
      validatePrice(price);
      out.add(new RegisteredModel(id, m.label() == null || m.label().isBlank() ? id : m.label(), price));
    }
    return List.copyOf(out);
  }

  static String priceEnvKey(String model) {
    return "HARNESS_PRICE_" + model.toUpperCase(Locale.ROOT).replaceAll("[^A-Z0-9]", "_");
  }

  static void validatePrice(String price) {
    if (price == null || price.isBlank()) {
      return;
    }
    String[] parts = price.split(",");
    if (parts.length != 2 && parts.length != 4 && parts.length != 8) {
      throw new CliException(
          2, 400, "price must be 2, 4, or 8 comma-separated USD-per-Mtok values");
    }
    for (String part : parts) {
      try {
        Double.parseDouble(part.trim());
      } catch (NumberFormatException e) {
        throw new CliException(2, 400, "price values must be numbers");
      }
    }
  }

  private static String normalizeId(String id, String what) {
    if (id == null || id.isBlank()) {
      throw new CliException(2, 400, what + " required");
    }
    String trimmed = id.trim();
    if (!PROVIDER_ID.matcher(trimmed).matches()) {
      throw new CliException(2, 400, "invalid " + what + " (use lowercase letters, digits, hyphens)");
    }
    return trimmed;
  }

  private static String normalizeModelId(String id) {
    if (id == null || id.isBlank()) {
      throw new CliException(2, 400, "model id required");
    }
    String trimmed = id.trim();
    if (trimmed.contains("..") || !MODEL_ID.matcher(trimmed).matches()) {
      throw new CliException(2, 400, "invalid model id");
    }
    return trimmed;
  }

  private static String blankToNull(String s) {
    if (s == null) {
      return null;
    }
    String t = s.trim();
    return t.isEmpty() ? null : t;
  }

  private static String firstNonBlank(String a, String b) {
    if (notBlank(a)) {
      return a.trim();
    }
    return blankToNull(b);
  }

  private static boolean notBlank(String s) {
    return s != null && !s.isBlank();
  }

  private static String nvl(String s, String fallback) {
    return s == null || s.isBlank() ? fallback : s;
  }

  private static String hint(String secret) {
    if (secret.length() <= 4) {
      return "set";
    }
    return "…" + secret.substring(secret.length() - 4);
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  private record StoredCatalog(List<StoredProvider> providers) {}

  @JsonIgnoreProperties(ignoreUnknown = true)
  private record StoredProvider(
      String id, String label, String adapter, String baseUrl, List<RegisteredModel> models) {}
}
