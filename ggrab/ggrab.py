#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""
ggrab hybrid CLI:
  usage: ggrab file1.py funcA funcB file2.js funcC ...

 - If token is recognized as a file, that becomes the "active file."
 - Subsequent tokens are function/class names for that file, until the user picks another file.
 - Auto-completion suggests:
     * function names for the current "active file"
     * file names (so you can start a new file)
 - Finally, we extract the specified functions from each file or the entire file if no functions are given.

Requires:
  - argcomplete (for auto-completion)
  - esprima (for JS parsing)
  - optional: pyperclip (for clipboard)
Usage:
  chmod +x ggrab.py
  eval "$(register-python-argcomplete ggrab.py)"
  ggrab file1.py funcA file2.js anotherFunc
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path
import time
import fnmatch

try:
    import argcomplete
except ImportError:
    # If argcomplete isn't installed, completions won't work, but script still runs
    pass

CACHE_FILE = os.path.expanduser("~/.ggrab_cache.json")


# Lazy imports
_ast = None
_esprima = None
_pyperclip = None
_tiktoken = None


SUPPORTED_EXTENSIONS = {
    # Python
    ".py",
    ".pyi",   # Type stubs
    ".pyw",   # Python on Windows

    # JavaScript
    ".js",
    ".mjs",   # ES modules
    ".cjs",   # CommonJS modules
    ".jsx",   # React JSX

    # TypeScript
    ".ts",
    ".tsx",   # React TSX

    # HTML/CSS/Other Web
    ".html",
    ".htm",
    ".xhtml",
    ".shtml",
    ".css",
    ".scss",
    ".sass",

    # Java & JVM languages
    ".java",
    ".scala",
    ".kt",    # Kotlin
    ".kts",   # Kotlin script

    # C / C++
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cc",
    ".hh",
    ".cxx",
    ".hxx",

    # C#
    ".cs",

    # Go
    ".go",

    # Rust
    ".rs",
    ".rlib",

    # PHP
    ".php",
    ".phtml",
    ".php4",
    ".php5",
    ".php7",
    ".php8",

    # Ruby
    ".rb",
    ".erb",

    # Perl
    ".pl",
    ".pm",
    ".t",     # Perl test scripts

    # Shell
    ".sh",
    ".bash",
    ".zsh",
    ".fish",

    # Lua
    ".lua",

    # Swift
    ".swift",

    # R
    ".R",
    ".r",
    ".Rmd",   # R Markdown (mix of code + text)

    # Julia
    ".jl",

    # Haskell
    ".hs",
    ".lhs",   # Literate Haskell

    # Erlang/Elixir
    ".erl",
    ".hrl",
    ".ex",
    ".exs",

    # Dart
    ".dart",

    # YAML / JSON / TOML (often config, but can contain code-like content)
    ".yaml",
    ".yml",
    ".json",
    ".toml",

    # Docker / Container
    ".dockerfile",  # Not always standard, often just 'Dockerfile'
    # If you want to capture Dockerfiles that have no extension:
    # you might handle them by name-check rather than extension

    # Make / Build
    ".mk",     # Makefiles (sometimes just named `Makefile` with no extension)
    ".cmake",
    ".gradle",
    ".csproj", # C# project files
    ".vbproj", # VB project files
    ".nuspec",

    # Documentation & Text
    ".txt",    # Plain text
    ".md",     # Markdown
    ".mdx",    # MDX (Markdown with JSX)
    ".rst",    # reStructuredText
    ".adoc",   # AsciiDoc
    ".textile", # Textile markup
    ".wiki",   # Wiki markup

    # Misc
    ".sql",
    ".dbml",
    ".vb",
    ".pas",    # Pascal / Delphi
    ".pp",     # Free Pascal

    # Web Development
    ".vue",    # Vue.js components
    ".svelte", # Svelte components
    ".astro",  # Astro components
    ".liquid", # Liquid templates
    ".ejs",    # Embedded JavaScript templates
    ".pug",    # Pug templates
    ".jade",   # Jade templates (old name for Pug)
    ".haml",   # Haml templates
    ".twig",   # Twig templates
    ".xml",    # XML files
    ".svg",    # SVG files
    ".less",   # Less CSS
    ".styl",   # Stylus CSS

    # Config & Data
    ".ini",    # INI configuration
    ".env",    # Environment variables
    ".conf",   # Configuration files
    ".cfg",    # Configuration files
    ".properties", # Java properties
    ".xml",    # XML files
    ".graphql", # GraphQL schemas
    ".proto",   # Protocol Buffers

    # Shell & Scripts
    ".ps1",    # PowerShell
    ".psm1",   # PowerShell module
    ".bat",    # Windows batch
    ".cmd",    # Windows command
    ".ksh",    # Korn shell

    # Infrastructure & DevOps
    ".tf",     # Terraform
    ".hcl",    # HashiCorp Configuration Language
    ".nomad",  # Nomad job files
    ".vault",  # Vault config
    ".helm",   # Helm charts
    ".k8s",    # Kubernetes manifests
    ".yaml.tpl", # YAML templates
    
    # Documentation & Text (expanding existing)
    ".org",    # Org mode
    ".pod",    # Perl POD documentation
    ".tex",    # LaTeX documents
    ".nfo",    # Info files
    ".log",    # Log files
    ".man",    # Manual pages

    # Database
    ".ddl",    # Data Definition Language
    ".dml",    # Data Manipulation Language
    ".pgsql",  # PostgreSQL
    ".mysql",  # MySQL
    ".sqlite", # SQLite

}

SPECIAL_FILENAMES = {
    # Build & Project Files
    "Makefile",
    "makefile",
    "Dockerfile",
    "dockerfile",
    "configure",
    "Rakefile",
    "Gemfile",

    # Config Files
    ".env",
    ".gitignore",
    ".dockerignore",
    ".editorconfig",
    ".eslintrc",
    ".prettierrc",
    ".babelrc",
    ".npmrc",
    ".yarnrc",

    # CI/CD & DevOps
    "Jenkinsfile",
    "Vagrantfile",
    "Procfile",

    # Documentation
    "README",
    "LICENSE",
    "CHANGELOG",
    "CONTRIBUTING",
    "AUTHORS",
    "PATENTS",
    "NOTICE"
}


def lazy_import_ast():
    global _ast
    if _ast is None:
        import ast
        _ast = ast
    return _ast


def lazy_import_esprima():
    global _esprima
    if _esprima is None:
        import esprima
        _esprima = esprima
    return _esprima


def lazy_import_pyperclip():
    global _pyperclip
    if _pyperclip is None:
        import pyperclip
        _pyperclip = pyperclip
    return _pyperclip


def lazy_import_tiktoken():
    """
    Lazy import for tiktoken. 
    If tiktoken is not installed, we'll set _tiktoken to None.
    """
    global _tiktoken
    if _tiktoken is None:
        try:
            import tiktoken
            _tiktoken = tiktoken
        except ImportError:
            _tiktoken = None
    return _tiktoken


def load_cache():
    """Load file->symbols cache from disk."""
    if not os.path.isfile(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_cache(cache):
    """Save file->symbols cache to disk."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except:
        pass


def is_file_candidate(token):
    """Return True if `token` is an existing file path."""
    return os.path.isfile(token)


def quick_extract_symbols(filepath):
    """
    Quick parse for function/class names in Python or JS (regex-based).
    For autocompletion only; actual extraction uses AST or esprima.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in (".py", ".js"):
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except:
        return []

    if ext == ".py":
        defs = re.findall(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", content, re.MULTILINE)
        clss = re.findall(r"^\s*class\s+([A-Za-z_]\w*)\s*[\(:]", content, re.MULTILINE)
        return sorted(set(defs + clss))
    else:  # .js
        funcs = re.findall(r"\bfunction\s+([A-Za-z_]\w*)\s*\(", content)
        clss = re.findall(r"\bclass\s+([A-Za-z_]\w*)\b", content)
        return sorted(set(funcs + clss))


def get_symbols_for_file(filepath):
    """
    Return symbol list from cache or do quick parse if stale.
    Cache expires if:
    1. File mtime has changed
    2. Cache entry is older than 1 minute
    """
    abspath = str(Path(filepath).resolve())
    cache = load_cache()
    try:
        current_mtime = os.path.getmtime(abspath)
        current_time = time.time()
    except:
        return []

    if abspath in cache:
        entry = cache[abspath]
        cache_age = current_time - entry.get("cached_at", 0)
        if (entry.get("mtime") == current_mtime and 
            cache_age < 60):  # 60 seconds = 1 minute
            return entry.get("symbols", [])

    symbols = quick_extract_symbols(abspath)
    cache[abspath] = {
        "mtime": current_mtime,
        "symbols": symbols,
        "cached_at": current_time
    }
    save_cache(cache)
    return symbols


def python_extract(filepath, symbols):
    """Accurate extraction of symbols from a Python file using AST."""
    ast = lazy_import_ast()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except:
        return [("whole-file", f"# Could not read file: {filepath}")]

    if not symbols:
        # entire file
        return [("whole-file", source)]

    try:
        tree = ast.parse(source, filename=filepath)
    except Exception as e:
        return [("error", f"# AST parse error in {filepath}: {e}")]

    lines = source.splitlines()
    found = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if node.name in symbols:
                snippet = snippet_from_node(node, lines)
                found.append((node.name, snippet))
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            if node.name in symbols:
                snippet = snippet_from_node(node, lines)
                found.append((node.name, snippet))
            self.generic_visit(node)

        def visit_ClassDef(self, node):
            if node.name in symbols:
                snippet = snippet_from_node(node, lines)
                found.append((node.name, snippet))
            self.generic_visit(node)

    Visitor().visit(tree)
    if not found:
        return [("error", f"# No matching symbols found in {filepath} for {symbols}")]
    return found


def snippet_from_node(node, lines):
    start = node.lineno - 1
    end = getattr(node, "end_lineno", start + 1)
    return "\n".join(lines[start:end])


def js_extract(filepath, symbols):
    """Accurate extraction of symbols from JS via esprima."""
    esprima = lazy_import_esprima()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except:
        return [("whole-file", f"// Could not read file: {filepath}")]

    if not symbols:
        # entire file
        return [("whole-file", source)]

    try:
        tree = esprima.parseModule(source, tolerant=True, loc=True)
    except Exception as e:
        return [("error", f"// esprima parse error in {filepath}: {e}")]

    lines = source.splitlines()
    found = []

    def node_name(n):
        if n.type == "FunctionDeclaration" and n.id:
            return n.id.name
        if n.type == "ClassDeclaration" and n.id:
            return n.id.name
        return None

    def walk(n):
        if hasattr(n, "body") and isinstance(n.body, list):
            for c in n.body:
                walk(c)
        nm = node_name(n)
        if nm and nm in symbols:
            start_line = n.loc.start.line
            end_line = n.loc.end.line
            snippet = "\n".join(lines[start_line - 1 : end_line])
            found.append((nm, snippet))

    walk(tree)
    if not found:
        return [("error", f"// No matching symbols found in {filepath} for {symbols}")]
    return found


def extract_file(filepath, symbols):
    """Extract requested symbols (or entire file) from one file."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".py":
        results = python_extract(filepath, symbols)
    elif ext == ".js":
        results = js_extract(filepath, symbols)
    else:
        # entire file
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                # Add warning if symbols were requested but can't be extracted
                if symbols:
                    warning = f"# Note: Symbol extraction not supported for {ext} files. Returning entire file."
                    content = f"{warning}\n\n{content}"
                results = [("whole-file", content)]
        except:
            results = [("whole-file", f"# Could not read file: {filepath}")]

    # Check if this was an error result and add status
    if len(results) == 1 and results[0][0] == "error":
        return results, False
    return results, True


def copy_to_clipboard(text):
    """Try copying to clipboard if pyperclip is installed."""
    try:
        lazy_import_pyperclip()
        _pyperclip.copy(text)
    except ImportError:
        pass


# -------------------
# Autocomplete Logic
# -------------------
def items_completer(prefix, parsed_args, **kwargs):
    import sys, os

    # Find the most recent file in parsed_args.items by looking from back to front
    active_file = None
    for item in reversed(parsed_args.items):
        if os.path.isfile(item):
            active_file = item
            break
    
    # Also check if prefix is itself a file
    if os.path.isfile(prefix):
        active_file = prefix

    # Build suggestions
    file_suggestions = _file_completions(prefix)
    func_suggestions = []
    if active_file and os.path.isfile(active_file):
        all_funcs = get_symbols_for_file(active_file)
        func_suggestions = [f for f in all_funcs if f.startswith(prefix)]

    suggestions = sorted(set(file_suggestions + func_suggestions))

    # Pre-cache if there's exactly one suggestion which is a file
    if len(suggestions) == 1 and os.path.isfile(suggestions[0]):
        from threading import Thread
        Thread(target=get_symbols_for_file, args=(suggestions[0],), daemon=True).start()

    return suggestions


def _file_completions(prefix):
    """Basic file completions for partial prefix."""
    if 'argcomplete' in sys.modules:
        from argcomplete.completers import FilesCompleter
        return FilesCompleter()(prefix)
    else:
        dir_part = os.path.dirname(prefix) or '.'
        base_part = os.path.basename(prefix)
        results = []
        try:
            for entry in os.listdir(dir_part):
                if entry.startswith(base_part):
                    full = os.path.join(dir_part, entry)
                    if os.path.isfile(full):
                        results.append(full)
        except:
            pass
        return results


# -------------------
# Token Counting Helper
# -------------------
def count_tokens(text):
    """
    Count tokens in the given text using tiktoken, if available.
    If tiktoken is missing or fails, return 0.
    """
    tk = lazy_import_tiktoken()
    if tk is None:
        return 0
    try:
        enc = tk.encoding_for_model("gpt-3.5-turbo")
        return len(enc.encode(text))
    except:
        return 0



def is_dir_candidate(token):
    """Return True if `token` is an existing directory."""
    return os.path.isdir(token)

def collect_code_files_in_dir(directory, ignore_pattern=None):
    """
    Recursively gather all files in 'directory' whose extension
    is in SUPPORTED_EXTENSIONS or whose filename is in SPECIAL_FILENAMES.
    If ignore_pattern is provided, interpret it as a shell glob and skip matching files.
    """
    code_files = []

    ignore_re = None
    if ignore_pattern:
        # Convert the user's shell glob pattern into a Python regex
        glob_regex = fnmatch.translate(ignore_pattern)
        try:
            ignore_re = re.compile(glob_regex)
        except re.error as e:
            print(f"[WARN] Invalid shell glob for --ignore: '{ignore_pattern}' => {e}")
            ignore_re = None

    for root, dirs, files in os.walk(directory):
        for filename in files:
            filepath = os.path.join(root, filename)

            # If ignoring pattern is set, skip if it matches
            if ignore_re and ignore_re.search(filepath):
                continue

            # Check both extension and special filenames
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUPPORTED_EXTENSIONS or filename in SPECIAL_FILENAMES:
                code_files.append(os.path.abspath(filepath))

    return code_files


# -------------------
# Main
# -------------------
def main():
    parser = argparse.ArgumentParser(
        description="ggrab: file1.py funcA funcB file2.py funcC => extracts code from each file or specific functions. Also supports directories."
    )
    items_arg = parser.add_argument(
        "items",
        nargs="*",
        help="Files and function names intermixed. Each file remains 'active' until the next file."
    )
    # the ignore flag
    parser.add_argument(
        "--ignore",
        "-i",
        default=None,
        help="Regex to ignore files (by name or path) when scanning directories."
    )

    if 'argcomplete' in sys.modules:
        items_arg.completer = items_completer
        argcomplete.autocomplete(parser)

    args = parser.parse_args()
    if not args.items:
        parser.print_help()
        sys.exit(0)

    # We'll parse the items left-to-right:
    #  - If we see a file, that becomes the "active file."
    #  - Next tokens are function names for that file, until we see another file, etc.
    results = {}  # file -> list of function names
    current_file = None
    for item in args.items:
        if is_dir_candidate(item):
            # Pass the ignore pattern when scanning directories
            dir_files = collect_code_files_in_dir(item, ignore_pattern=args.ignore)
            for f in dir_files:
                results.setdefault(f, [])
            current_file = None  # Reset active file after directory
        elif is_file_candidate(item):
            current_file = item
            results.setdefault(current_file, [])
        else:
            # function name for current file
            if current_file is not None:
                results[current_file].append(item)

    final_blocks = []
    summary_lines = []
    file_token_data = {}
    grand_total_tokens = 0
    grand_total_lines = 0  # Add line counter

    # Extract code and count tokens all in one pass
    current_file = None
    current_blocks = []
    
    for f, funcs in results.items():
        snippet_list, success = extract_file(f, funcs)

        # Update bookkeeping to include lines
        file_token_data[f] = {
            "total_tokens": 0,
            "total_lines": 0,  
            "functions": {},
            "error": not success
        }

        # Summaries
        if funcs:
            summary_lines.append(f"- {f}, functions: {', '.join(funcs)}")
        else:
            summary_lines.append(f"- {f}, entire file")

        # Combine all snippets for this file
        file_content = []
        for (sym, code) in snippet_list:
            n_tokens = count_tokens(code)
            lines_in_snippet = code.count('\n') + 1  # Count lines

            file_token_data[f]["total_tokens"] += n_tokens
            file_token_data[f]["total_lines"] += lines_in_snippet

            # Track function-level tokens and lines if applicable
            if sym not in (None, "whole-file", "error"):
                file_token_data[f]["functions"][sym] = {
                    "tokens": n_tokens,
                    "lines": lines_in_snippet,
                }
            
            file_content.append(code)

        # Add combined file content to final blocks
        combined_content = "\n\n".join(file_content)
        final_blocks.append(f"<file name=\"{f}\">\n{combined_content}\n</file>")

        grand_total_tokens += file_token_data[f]["total_tokens"]
        grand_total_lines += file_token_data[f]["total_lines"]  # Add to total

    # Print combined summary with token counts
    print("Gathered code from:")
    for f in results.keys():
        ext = os.path.splitext(f)[1].lower()
        total_tokens = file_token_data[f]["total_tokens"]
        total_lines = file_token_data[f]["total_lines"]
        
        if file_token_data[f]["error"]:
            print(f"  - {f}: No matching symbols found for {results[f]}")
            continue
            
        if results[f]:  # if there are specific functions
            if ext not in ('.py', '.js'):
                print(f"  - {f}: Symbol extraction not supported for {ext} files. "
                      f"Returning entire file. ({total_lines} lines, {total_tokens} tokens)")
            else:
                func_parts = []
                for func_name in results[f]:
                    fdata = file_token_data[f]["functions"].get(func_name, {})
                    func_lines = fdata.get("lines", 0)
                    func_tokens = fdata.get("tokens", 0)
                    func_parts.append(f"{func_name} [{func_lines} lines, {func_tokens} tokens]")
                func_str = ", ".join(func_parts)
                print(f"  - {f}, functions: {func_str} "
                      f"(file total: {total_lines} lines, {total_tokens} tokens)")
        else:
            print(f"  - {f}, entire file ({total_lines} lines, {total_tokens} tokens)")

    # Updated totals
    print(f"\nTotal lines across all files: {grand_total_lines}")
    print(f"Total tokens across all files: {grand_total_tokens}")

    print("\n===== Combined Snippets (copied to clipboard) =====\n")

    # Combine extracted snippets
    combined = "\n\n".join(final_blocks)

    # Copy to clipboard
    copy_to_clipboard(combined)


if __name__ == "__main__":
    main()
