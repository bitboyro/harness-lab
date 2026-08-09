# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [semver](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Field runs record `target`, `pack_name`, and `pack_path` in `manifest.json`
  (credentials stripped from URLs) so `harness compare` can name what changed
  when the same tasks run against different servers. Controlled runs omit the
  keys. See [docs/test-your-api-harness.md](./docs/test-your-api-harness.md).

## [0.0.1] — 2026-08-09

First release. See the [README](./README.md) for what it does.

[0.0.1]: https://github.com/bitboyro/harness-lab/releases/tag/v0.0.1
[Unreleased]: https://github.com/bitboyro/harness-lab/compare/v0.0.1...HEAD
