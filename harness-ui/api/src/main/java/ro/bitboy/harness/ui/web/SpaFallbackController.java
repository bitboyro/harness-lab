package ro.bitboy.harness.ui.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * Forward non-API GETs to {@code index.html} so deep links survive refresh
 * against the Next static export under {@code classpath:/static/}.
 */
@Controller
public class SpaFallbackController {

  @GetMapping(value = {
      "/",
      "/{path:^(?!api|artifacts|v3|swagger-ui|swagger-ui\\.html).*$}",
      "/{path:^(?!api|artifacts|v3|swagger-ui).*$}/**"
  })
  public String spa() {
    return "forward:/index.html";
  }
}
