# harness-ui API (S2)

Spring Boot 3.3 / Java 21 control plane. REST only — MCP `@Tool` is S5.

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21 2>/dev/null || echo /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home)
./mvnw verify
./mvnw spring-boot:run -Dharness.data=/tmp/harness-data \
  -Dharness.adapter-script=$PWD/../adapter/harness_json.py
```

Loopback: `http://127.0.0.1:8085`. OpenAPI: `/v3/api-docs`.
