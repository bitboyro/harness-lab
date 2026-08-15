# harness-ui API (S2)

Spring Boot 3.3 / Java 21 control plane. REST + MCP JSON-RPC at `POST /mcp`.

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21 2>/dev/null || echo /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home)
./mvnw verify
./mvnw spring-boot:run -Dharness.data=/tmp/harness-data \
  -Dharness.adapter-script=$PWD/../adapter/harness_json.py

# Local dev (from harness-ui/api/, with repo venv):
./mvnw spring-boot:run \
  -Dspring-boot.run.arguments="\
--harness.data=$PWD/../harness-data \
--harness.cli=$PWD/../../.venv/bin/harness \
--harness.adapter=$PWD/../../.venv/bin/python \
--harness.adapter-script=$PWD/../adapter/harness_json.py"

# Or from repo root: harness-ui/scripts/dev-start.sh
```

Loopback: `http://127.0.0.1:8085`. OpenAPI: `/v3/api-docs`. MCP: `POST /mcp` (`tools/list`, `tools/call`).
