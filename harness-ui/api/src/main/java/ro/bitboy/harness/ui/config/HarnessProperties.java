package ro.bitboy.harness.ui.config;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "harness")
public class HarnessProperties {

  /** Workspace root for targets, packs, results, jobs. */
  private Path data = Path.of("/data");

  /** Executable name or path for the harness CLI. */
  private String cli = "harness";

  /** Python interpreter used to spawn the adapter. */
  private String adapter = "python3";

  /** Absolute or relative path to {@code harness_json.py}. */
  private Path adapterScript = Path.of("/app/adapter/harness_json.py");

  /** Pinned harness wheel version asserted by the adapter. */
  private String expectVersion = "0.0.1";

  /**
   * Override harness {@code --disk-reserve-gb} on spawned runs. Null keeps CLI
   * defaults (5 GB for full matrices; 0 for smoke/probe).
   */
  private Double diskReserveGb;

  public Path getData() {
    return data;
  }

  public void setData(Path data) {
    this.data = data;
  }

  public String getCli() {
    return cli;
  }

  public void setCli(String cli) {
    this.cli = cli;
  }

  public String getAdapter() {
    return adapter;
  }

  public void setAdapter(String adapter) {
    this.adapter = adapter;
  }

  public Path getAdapterScript() {
    return adapterScript;
  }

  public void setAdapterScript(Path adapterScript) {
    this.adapterScript = adapterScript;
  }

  public String getExpectVersion() {
    return expectVersion;
  }

  public void setExpectVersion(String expectVersion) {
    this.expectVersion = expectVersion;
  }

  public Double getDiskReserveGb() {
    return diskReserveGb;
  }

  public void setDiskReserveGb(Double diskReserveGb) {
    this.diskReserveGb = diskReserveGb;
  }

  public Path targetsDir() {
    return data.resolve("targets");
  }

  public Path packsDir() {
    return data.resolve("packs");
  }

  public Path resultsDir() {
    return data.resolve("results");
  }

  public Path jobsDir() {
    return data.resolve("jobs");
  }

  public Path compareDir() {
    return data.resolve("compare");
  }

  public Path generateDir() {
    return data.resolve("generate");
  }

  /** Staging tokens for generate/fixture subprocesses (G6.2). */
  public Path secretsDir() {
    return data.resolve("secrets");
  }

  /** Non-secret UI catalog (LLM provider profiles, registered models). */
  public Path configDir() {
    return data.resolve("config");
  }
}
