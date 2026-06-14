#!/bin/zsh
set -e

cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
    echo "Create .venv with Python 3.11 or newer first."
    exit 1
fi

.venv/bin/python -m pip install -e . pyinstaller
.venv/bin/pyinstaller --noconfirm --clean "Clip Board.spec"

mkdir -p "$HOME/Applications"
clean_root="$(mktemp -d)"
trap 'rm -rf "$clean_root"' EXIT
COPYFILE_DISABLE=1 tar -C dist -cf - "Clip Board.app" \
    | COPYFILE_DISABLE=1 tar -C "$clean_root" -xf -
codesign --force --deep --sign - "$clean_root/Clip Board.app"

rm -rf "$HOME/Applications/Clip Board.app"
ditto "$clean_root/Clip Board.app" "$HOME/Applications/Clip Board.app"

lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$lsregister" ]]; then
    "$lsregister" -f "$HOME/Applications/Clip Board.app"
fi

echo "Installed: $HOME/Applications/Clip Board.app"
open "$HOME/Applications/Clip Board.app"
