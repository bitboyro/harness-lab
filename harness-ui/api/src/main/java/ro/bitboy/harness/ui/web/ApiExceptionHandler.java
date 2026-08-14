package ro.bitboy.harness.ui.web;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import ro.bitboy.harness.ui.core.CliException;

@RestControllerAdvice
public class ApiExceptionHandler {

  @ExceptionHandler(CliException.class)
  public ResponseEntity<Map<String, Object>> handleCli(CliException e) {
    return ResponseEntity.status(e.getHttpStatus()).body(Map.of(
        "error", e.getMessage() == null ? "error" : e.getMessage(),
        "exitCode", e.getExitCode()));
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<Map<String, Object>> handleValidation(MethodArgumentNotValidException e) {
    String msg = e.getBindingResult().getFieldErrors().stream()
        .findFirst()
        .map(err -> err.getField() + ": " + err.getDefaultMessage())
        .orElse("validation failed");
    return ResponseEntity.badRequest().body(Map.of("error", msg, "exitCode", 2));
  }

  @ExceptionHandler(IllegalArgumentException.class)
  public ResponseEntity<Map<String, Object>> handleIllegal(IllegalArgumentException e) {
    return ResponseEntity.badRequest().body(Map.of(
        "error", e.getMessage() == null ? "bad request" : e.getMessage(),
        "exitCode", 2));
  }
}
