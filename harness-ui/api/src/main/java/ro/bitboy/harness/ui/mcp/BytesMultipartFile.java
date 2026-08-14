package ro.bitboy.harness.ui.mcp;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.web.multipart.MultipartFile;

/** Minimal MultipartFile for MCP base64 uploads — avoids test-scoped MockMultipartFile in main code. */
final class BytesMultipartFile implements MultipartFile {

  private final String name;
  private final String originalFilename;
  private final String contentType;
  private final byte[] bytes;

  BytesMultipartFile(String name, String originalFilename, String contentType, byte[] bytes) {
    this.name = name;
    this.originalFilename = originalFilename;
    this.contentType = contentType;
    this.bytes = bytes == null ? new byte[0] : bytes;
  }

  @Override
  public String getName() {
    return name;
  }

  @Override
  public String getOriginalFilename() {
    return originalFilename;
  }

  @Override
  public String getContentType() {
    return contentType;
  }

  @Override
  public boolean isEmpty() {
    return bytes.length == 0;
  }

  @Override
  public long getSize() {
    return bytes.length;
  }

  @Override
  public byte[] getBytes() {
    return bytes;
  }

  @Override
  public InputStream getInputStream() {
    return new ByteArrayInputStream(bytes);
  }

  @Override
  public void transferTo(File dest) throws IOException {
    throw new UnsupportedOperationException("transferTo not supported");
  }
}
