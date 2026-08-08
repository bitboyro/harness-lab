# Install

There is one thing to download, not two. The release zip contains the wheel and
the installer together, so `install.py` never has to fetch anything and never
needs credentials. If you would rather pull the wheel from GitHub, `--download`
does that — see [From a GitHub release](#from-a-github-release).

## From the bundle

You have `harness-lab-<version>.zip`. Unzip it and run the installer, which
checks the machine before it changes anything:

```bash
python3 install.py --check     # report only: what is missing, and what it blocks
python3 install.py             # install the wheel sitting next to it
```

The wheel is already inside the zip, next to `install.py` — that is what
"beside it" means. Nothing is downloaded, so this works offline and on a
machine with no GitHub access.

`install.py` runs on **any** Python 3 — including one too old to run harness —
so an old interpreter gets an explanation rather than a `SyntaxError`:

```
[MISS] python    3.9.6 at /usr/bin/python3
       needs 3.11 or newer
  macOS:    brew install python@3.12
  Debian:   sudo apt install python3.12 python3.12-venv
```

Into a virtualenv (recommended):

```bash
python3 -m venv .venv
.venv/bin/python install.py
```

Or onto the user site, if a virtualenv is not an option:

```bash
python3 install.py --user
```

## From a GitHub release

If you have the repo but not a bundle, skip the build:

```bash
python3 install.py --download            # latest release
python3 install.py --tag=v0.0.1          # a specific one
```

No credentials, no `gh`, no extra tooling — it reads the public releases API
and writes the wheel to a temp directory. If it reports a 403, that is the
anonymous rate limit (60 requests an hour per IP); wait, or take the release
zip from the [releases page](https://github.com/bitboyro/harness-lab/releases)
by hand.

## From a wheel directly

The wheel is `py3-none-any` — one file, every OS, every Python 3.11+:

```bash
pip install harness_lab-0.0.1-py3-none-any.whl[openai]
```

## From a checkout

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,openai]'
.venv/bin/python -m pytest -q      # ~12s, no network, no API key
```

Editing the mock API's *domain* — its entities, routes and seeded world — means
working from a checkout. Its *shape* (`--cores`, `--fan-out`, `--surface-size`,
`--difficulty`, `--seed`) is a parameter everywhere.

## Running it

Two forms, and no third:

```bash
harness lint --demo
python3 -m harness lint --demo
```

The second always works. The first needs the install's script directory on
PATH, which a virtualenv nobody activated will not have — `install.py` prints
the exact `export PATH=...` line for your machine if so.

## Checking the environment

```bash
harness doctor
```

Reports Python, the package, its dependencies, your API key, `curl`, `git` and
free disk — and for anything missing, **what that specific thing blocks**:

```
[ok  ] curl      /usr/bin/curl
[warn] api key   no OPENAI_API_KEY
                 ↳ blocks: any run that calls a model. `lint` does not need one
```

It exits non-zero only when something *required* is absent, so it is safe in a
health check. It imports no provider SDK and touches no network — it has to
work when the install is broken, which is the only time anyone runs it.

## Requirements

- **Python 3.11+.** Stock macOS ships 3.9.
- **`curl` on PATH** for the C arms, which shell out to it.
- **`git`** for authored-skill provenance; the `-auth` arms record
  `uncommitted` without it.
- An **`OPENAI_API_KEY`** for anything that calls a model. `harness lint` needs
  none.

Credentials go in `.env` at the working directory (gitignored; copy
`.env.example`). Nothing needs exporting — the CLI loads `.env` and prints which
names it found, never their values.

## A warning worth reading first

The **D arms execute model-written Python** via a subprocess in a temp
directory, with **no container isolation**. It is the model's own code against a
local mock, but run it somewhere you are comfortable with that. `--presets`
without `D1`/`D2` avoids it entirely.

## Check it works

```bash
harness doctor
harness lint --demo                              # free, no key, one second
harness run --out /tmp/s --id s --smoke --yes    # ~12 runs, ~1 min, ~$0.05
```

The smoke run proves the pipeline end to end. It is not a result — three arms
over two cores cannot resolve any contrast.

---

Next: [test-your-api-harness.md](./test-your-api-harness.md) to test your own API, or
[controlled-rig.md](./controlled-rig.md) for the built-in experiment.
