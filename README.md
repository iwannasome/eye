# eye

just spinning eye in your terminal

## Install

Requires **Python 3.10 or newer**. No Git, WSL, or virtual environment activation is needed.

### Windows

Install [Python](https://www.python.org/downloads/windows/) if it is not already installed. Open PowerShell or Command Prompt and run:

```powershell
py -m pip install --user pipx
py -m pipx install https://github.com/iwannasome/eye/archive/refs/heads/main.zip
py -m pipx ensurepath
```

If `py` is not recognized but `python` works, replace `py` with `python` in all three commands.

### Linux / macOS

Install [pipx](https://pipx.pypa.io/latest/how-to/install-pipx.html) with your package manager:

| System | Command |
| --- | --- |
| Fedora | `sudo dnf install pipx` |
| Ubuntu / Debian | `sudo apt update && sudo apt install pipx` |
| macOS with Homebrew | `brew install pipx` |

Then install eye:

```sh
pipx install https://github.com/iwannasome/eye/archive/refs/heads/main.zip
pipx ensurepath
```

**After installation, close your terminal application completely and reopen it.** This lets the terminal find the new `eye` command. You only need to install once.

## Run

From any folder:

```sh
eye
```

Only the rotating eye, without the HUD:

```sh
eye --no-hud
```

Choose a color, optionally without the HUD:

```sh
eye --color cyan
eye --color red --no-hud
```

Available colors: `purple`, `blue`, `cyan`, `green`, `lime`, `yellow`, `orange`, `red`, `pink`, `white`.

## Controls

| Key | Action |
| --- | --- |
| `C` | Next color |
| `H` | Hide / show the HUD |
| `Space` | Pause / resume |
| `Q` or `Ctrl+C` | Quit |

For less rendering work, use `eye --fps 15`. Run `eye --help` for all options.

If `eye` is not found, run `pipx ensurepath` again (`py -m pipx ensurepath` on Windows), then close and reopen the terminal application.

## Run without installing

Download [eye.py](https://raw.githubusercontent.com/iwannasome/eye/main/eye.py), open a terminal in its folder, and run `python eye.py` on Windows or `python3 eye.py` on Linux/macOS. This runs the file directly; installing as above is what makes the short `eye` command available everywhere.
