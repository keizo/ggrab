# ggrab - Grug Grab Tool

A CLI tool for manually building context to paste into llm chats. `ggrab` gathers functions, classes, or entire files wraps them with xml and copies it to the clipboard.

## Key Features

- **Smart Extraction:** Grab entire files or specific functions/classes
- **Intelligent Autocompletion:** File paths and function/class names
- **Token Counting:** Built-in token counting for AI context limits
- **Language Support:**
  - Python (AST-based extraction)
  - JavaScript (Esprima-based extraction)
  - Other files (full file extraction)

## Quick Start

1. **Install:**
```bash
pip install ggrab    # Basic install
# or
pipx install ggrab   # Recommended
```

> **Why pipx?** The `pipx` install is recommended because it:
> - Won't interfere with other Python projects (creates its own venv)
> - Makes ggrab available globally in your terminal

2. **Setup:**

Add the following to your shell config file (`~/.bashrc`, `~/.zshrc`, or equivalent):
```bash
# Enable ggrab autocompletion
eval "$(register-python-argcomplete ggrab)"
```

Then reload your shell configuration:
```bash
# For bash
source ~/.bashrc

# For zsh
source ~/.zshrc
```

## Usage

```bash
# Grab entire files
ggrab file.py

# Extract specific functions
ggrab file.py function1 function2

# Mix multiple files and functions
ggrab file1.py func1 func2 file2.js func3

# Now supports full directories (entire files only)
ggrab directory

# Skip files matching a pattern
ggrab directory/ --ignore *.test.*       # Skip test files
ggrab src/ -i node_modules         # Skip node_modules directory
ggrab . -i *.spec.*                # Skip spec files
ggrab . -i dist                    # Skip dist directory
ggrab . -i *.min.*                 # Skip minified files
ggrab . -i vendor                  # Skip vendor directory
ggrab . -i '*.generated.*'         # Skip generated files (quotes needed for *)
ggrab . -i "**/__pycache__/**"     # Skip Python cache dirs (quotes needed for **)
ggrab . -i '(dist|build)/*'        # Skip multiple dirs (quotes needed for special chars)

# Multiple patterns are also supported
ggrab . -i 'dist/*' -i 'build/*'                     # Can use multiple -i flags too
```

Press `TAB` at any time for smart autocompletion:
- After `ggrab`: Shows file suggestions
- After selecting a file: Shows available functions/classes

## Examples

```bash
# Extract multiple functions from a Python file
$ ggrab utils.py parse_data validate_input
Gathered code from:
  - utils.py, functions: parse_data, validate_input (203 tokens)

===== Combined Snippets (copied to clipboard) =====

# Extract from multiple files
$ ggrab api.py handle_request db.js queryDatabase
Gathered code from:
  - api.py, functions: handle_request (156 tokens)
  - db.js, functions: queryDatabase (178 tokens)

Total tokens across all files: 334
```

## Performance Features

- **Lazy Loading:** Heavy dependencies load only when needed
- **Smart Caching:** Function/class listings cached for quick access
- **Hybrid Parsing:** Fast regex for completion, accurate AST/Esprima for extraction

## Requirements

- Python 3.7+
- Required: `argcomplete`
- Optional but recommended:
  - `pyperclip` (clipboard support)
  - `tiktoken` (token counting)
  - `esprima` (JavaScript parsing)

## Advanced Setup

**Disable completion sorting** (optional):
```bash
complete -o nosort -F _python_argcomplete ggrab
```

**For zsh users:**
```bash
autoload -U compinit && compinit
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete ggrab)"
```

## Acknowledgments

- Developed -- ok, prompted into existance by Claude 3.5, o1 pro. Fixed up to working order by [Keizo Gates](https://github.com/keizo) making [GrugNotes](https://grugnotes.com) :)

## License

MIT License

---

For bug reports and feature requests, please open an issue on GitHub.