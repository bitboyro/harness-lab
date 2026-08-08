# Install

Three ways in, depending on whether you want to run it, keep it, or work on it.

## The single file

No install, no virtualenv. Download `harness-<version>-<platform>.pyz` from a
release and run it:

```bash
python3 harness.pyz --version
python3 harness.pyz lint --demo
```

The `.pyz` is platform-specific — it carries compiled wheels, so take the one
matching your machine. First run unpacks to `~/.shiv`; later runs are instant.

## As a tool on your PATH

```bash
curl -fsSL <raw-url>/install.sh | sh
```

Installs [uv](https://docs.astral.sh/uv/), fetches a Python if you have none new
enough, and installs `harness` as a tool. The repo is private, so set
`GITHUB_TOKEN` first, or have SSH access configured:

```bash
export GITHUB_TOKEN=ghp_...
curl -fsSL <raw-url>/install.sh | sh -s -- --ref v0.1.0
```

## From a checkout

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,openai]'
.venv/bin/python -m pytest -q      # ~12s, no network, no API key
```

Editing the mock API's *domain* — the entities, the routes, the seeded world —
means working from a checkout. Its *shape* (`--cores`, `--fan-out`,
`--surface-size`, `--difficulty`, `--seed`) is a parameter everywhere.

## Requirements

- **Python 3.11+.** Stock macOS ships 3.9; the `.pyz` says so rather than
  failing on an import.
- **`curl` on PATH** for the C arms, which shell out.
- **`git`** if you use an authored skill — provenance records the commit.
- An **`OPENAI_API_KEY`** for anything that runs a model. `harness lint` needs
  none.

Credentials go in `.env` at the repo root (gitignored; copy `.env.example`).
Nothing needs exporting — the CLI loads `.env` and prints which names it found,
never their values.

## A warning worth reading first

The **D arms execute model-written Python** via a subprocess in a temp
directory, with **no container isolation**. It is the model's own code against a
local mock, but run it somewhere you are comfortable with that. `--presets`
without `D1`/`D2` avoids it entirely.

## Check it works

```bash
harness lint --demo                 # free, no key, one second
harness run --out /tmp/s --id s --smoke --yes   # ~12 runs, ~1 min, ~$0.05
```

The smoke run proves the pipeline end to end. It is not a result — three arms
over two cores cannot resolve any contrast.

---

Next: [your-api.md](./your-api.md) to test your own API, or
[controlled-rig.md](./controlled-rig.md) for the built-in experiment.
