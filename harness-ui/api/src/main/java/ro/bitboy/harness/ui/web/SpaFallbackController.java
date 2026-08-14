package ro.bitboy.harness.ui.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

/**
 * Next {@code output: 'export'} only ships HTML for pre-rendered ids plus a
 * {@code _} shell. Deep links and full navigations to unknown ids must hit
 * that shell; the client reads the real id from {@code window.location}.
 *
 * <p>Paths with a file extension are left to the resource handler.
 */
@Controller
public class SpaFallbackController {

  @GetMapping("/")
  public String root() {
    return "forward:/index.html";
  }

  @GetMapping({"/experiments", "/experiments/"})
  public String experimentsIndex() {
    return "forward:/experiments/index.html";
  }

  @GetMapping({"/experiments/new", "/experiments/new/"})
  public String experimentsNew() {
    return "forward:/experiments/new/index.html";
  }

  @GetMapping({
      "/experiments/new/from-openapi",
      "/experiments/new/from-openapi/"
  })
  public String experimentsFromOpenApi() {
    return "forward:/experiments/new/from-openapi/index.html";
  }

  @GetMapping({"/compare", "/compare/"})
  public String compare() {
    return "forward:/compare/index.html";
  }

  @GetMapping({"/settings", "/settings/"})
  public String settings() {
    return "forward:/settings/index.html";
  }

  @GetMapping({"/settings/providers", "/settings/providers/"})
  public String settingsProviders() {
    return "forward:/settings/providers/index.html";
  }

  @GetMapping({"/runs/new", "/runs/new/"})
  public String runsNew() {
    return "forward:/runs/new/index.html";
  }

  @GetMapping({"/runs", "/runs/"})
  public String runsIndex() {
    return "forward:/runs/index.html";
  }

  @GetMapping({"/targets", "/targets/"})
  public String targetsIndex() {
    return "forward:/targets/index.html";
  }

  @GetMapping({"/runs/{id:[^\\.]+}", "/runs/{id:[^\\.]+}/"})
  public String runShell(@PathVariable String id) {
    return "forward:/runs/_/index.html";
  }

  /**
   * Artifact names often contain dots ({@code report.html}) and may nest
   * ({@code charts/score.svg}). Never treat the residual path as a static
   * file — the Next shell owns the route; the iframe loads the real file
   * from {@code /artifacts/{runId}/**}.
   *
   * <p>{@code id} excludes {@code _} so a forward to
   * {@code /runs/_/artifacts/_/index.html} is served by the static resource
   * handler instead of re-entering this mapping.
   */
  @GetMapping({
      "/runs/{id:^(?!_$).+}/artifacts/{name}",
      "/runs/{id:^(?!_$).+}/artifacts/{name}/"
  })
  public String artifactShell(@PathVariable String id, @PathVariable String name) {
    if (isFile(id)) {
      return null;
    }
    return "forward:/runs/_/artifacts/_/index.html";
  }

  @GetMapping("/runs/{id:^(?!_$).+}/artifacts/{dir}/{*rest}")
  public String artifactShellNested(@PathVariable String id) {
    if (isFile(id)) {
      return null;
    }
    return "forward:/runs/_/artifacts/_/index.html";
  }

  @GetMapping({"/packs", "/packs/"})
  public String packsIndex() {
    return "forward:/packs/index.html";
  }

  @GetMapping({"/packs/{id:[^\\.]+}", "/packs/{id:[^\\.]+}/"})
  public String packShell(@PathVariable String id) {
    if (isFile(id)) {
      return null;
    }
    return "forward:/packs/_/index.html";
  }

  @GetMapping({"/experiments/{id:[^\\.]+}", "/experiments/{id:[^\\.]+}/"})
  public String experimentShell(@PathVariable String id) {
    return "forward:/experiments/_/index.html";
  }

  @GetMapping({"/targets/{id:[^\\.]+}", "/targets/{id:[^\\.]+}/"})
  public String targetShell(@PathVariable String id) {
    if ("lint".equals(id)) {
      return null;
    }
    return "forward:/targets/_/index.html";
  }

  @GetMapping({"/targets/{id}/lint", "/targets/{id}/lint/"})
  public String lintShell(@PathVariable String id) {
    if (isFile(id)) {
      return null;
    }
    return "forward:/targets/_/lint/index.html";
  }

  @GetMapping({
      "/{path:^(?!api|artifacts|v3|swagger-ui|_next|runs|packs|targets|experiments|compare|settings)[^.]+$}",
      "/{path:^(?!api|artifacts|v3|swagger-ui|_next|runs|packs|targets|experiments|compare|settings)[^.]+$}/**"
  })
  public String other() {
    return "forward:/index.html";
  }

  private static boolean isFile(String segment) {
    return segment != null && segment.contains(".");
  }
}
