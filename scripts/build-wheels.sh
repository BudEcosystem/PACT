#!/usr/bin/env bash
# Build what PACT publishes to the package index, check it, and prove the wheels work installed.
#
#   ./scripts/build-wheels.sh                                  # this machine's architecture
#   ./scripts/build-wheels.sh --target x86_64-unknown-linux-gnu  # another one (built, not run)
#
# Into `dist/` (emptied first):
#
#   pact_loader-<v>-py3-none-manylinux_2_28_<arch>.whl   the `pact` binary, for one architecture
#   pact_loader-<v>.tar.gz                               its source: the Cargo workspace and the
#                                                        spec files the binary compiles in
#   pact_adapters-<v>-py3-none-any.whl                   the Python adapters, one wheel for
#                                                        every platform. No source distribution:
#                                                        the wheel carries `spec/schema.yaml` and
#                                                        `models/catalog.yaml` from outside its
#                                                        folder, which a build from one cannot reach
#
# The loader is built with zig as the linker (`maturin --zig`), so the binary asks for no glibc
# newer than 2.28 whatever machine builds it, and either architecture can be built on either.
# Then `twine check` reads every file's metadata as the index will, the loader's source
# distribution is built into a wheel on its own (it must carry everything it compiles in), and,
# when the target is this machine's architecture, the wheels are installed into a fresh
# environment outside the checkout, where `pact check` runs on a shipped example and
# `pact_adapters.loader.pact_binary()` finds the installed binary with no `PACT_BIN` and the
# environment's folder on no `PATH`.
#
# `.github/workflows/wheels.yml` runs exactly this, once per architecture. On a tag, the tag must
# be `v<version>`, the version every file here carries.
set -euo pipefail
cd "$(dirname "$0")/.."
unset PYTHONPATH PYTHONHOME

target="$(rustc -vV | sed -n 's/^host: //p')"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) target="$2"; shift 2 ;;
    *) echo "error: \`$1\` is not something build-wheels.sh takes. fix: --target <rust target triple>" >&2; exit 2 ;;
  esac
done
host="$(rustc -vV | sed -n 's/^host: //p')"
python="${PACT_WHEEL_PYTHON:-3.12}"
maturin=(uvx --from "maturin>=1.9,<2" --with "ziglang>=0.17,<0.18" maturin)

version="$(sed -n 's/^version = "\(.*\)"/\1/p' Cargo.toml | head -1)"
adapters="$(sed -n 's/^version = "\(.*\)"/\1/p' adapters/python/pyproject.toml | head -1)"
if [[ "$version" != "$adapters" ]]; then
  echo "error: the loader is $version (Cargo.toml) and pact-adapters is $adapters. fix: release them at one version" >&2
  exit 1
fi
if [[ "${GITHUB_REF_TYPE:-}" == tag && "${GITHUB_REF_NAME:-}" != "v$version" ]]; then
  echo "error: the tag is ${GITHUB_REF_NAME} and the version is $version. fix: tag v$version" >&2
  exit 1
fi

rm -rf dist && mkdir dist
rustup target add "$target" >/dev/null
"${maturin[@]}" build --release --zig --target "$target" --out dist
"${maturin[@]}" sdist --out dist
uv build --quiet --wheel --out-dir dist adapters/python
uvx twine check --strict dist/*
ls -l dist

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# The source distribution alone builds the loader: nothing it compiles in was left behind.
uv build --quiet --wheel --out-dir "$work/from-sdist" dist/pact_loader-"$version".tar.gz
echo "the loader's source distribution builds on its own"

if [[ "$target" != "$host" ]]; then
  echo "built for $target on $host: the wheel is installed and run on its own architecture"
  exit 0
fi
uv venv --quiet --seed --python "$python" "$work/venv"
"$work/venv/bin/python" -m pip install --quiet --disable-pip-version-check --find-links dist \
  "dist/pact_adapters-$version-py3-none-any.whl"
cp -r examples/refund-desk "$work/refund-desk"
cd "$work"
env -u PACT_BIN PATH=/usr/bin:/bin "$work/venv/bin/pact" check refund-desk --deny-warnings
env -u PACT_BIN PATH=/usr/bin:/bin "$work/venv/bin/python" - "$work/venv" <<'PY'
import sys
from importlib.metadata import version
from pathlib import Path

from pact_adapters.loader import pact_binary

found = pact_binary()
assert found == Path(sys.argv[1]) / "bin" / "pact", f"found {found}, not the wheel's loader"
print(f"pact-adapters {version('pact-adapters')} finds pact-loader {version('pact-loader')} at {found}")
PY
echo "installed: pact check passes on refund-desk, and the adapters find the wheel's loader"
