package ro.bitboy.harness.ui;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class HarnessUiApplication {

  public static void main(String[] args) {
    SpringApplication.run(HarnessUiApplication.class, args);
  }
}
