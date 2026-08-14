package ro.bitboy.harness.ui.dto;

import java.time.Instant;

public record Target(String id, String kind, String label, Instant createdAt) {}
