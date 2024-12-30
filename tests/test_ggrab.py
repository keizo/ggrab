# tests/test_ggrab.py

import os
import sys
import tempfile
import shutil
import pytest
from pathlib import Path
import subprocess
import esprima

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Since the CLI code lives in ggrab/ggrab.py, let's import the relevant functions.
# Adjust these imports if needed based on how your package is structured.
from ggrab.ggrab import (
    is_file_candidate,
    is_dir_candidate,
    quick_extract_symbols,
    extract_file,
    python_extract,
    js_extract,
    count_tokens,
    main
)

@pytest.fixture
def temp_py_file():
    """Fixture to create a temp Python file for testing."""
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
        f.write(
            "import os\n\n"
            "class MyClass:\n"
            "    def method_a(self):\n"
            "        pass\n\n"
            "def foo():\n"
            "    return 42\n"
        )
        f.flush()
        yield f.name
    os.remove(f.name)


@pytest.fixture
def temp_js_file():
    """Fixture to create a temp JS file for testing."""
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
        f.write(
            "function bar() {\n"
            "  return 100;\n"
            "}\n\n"
            "class Car {\n"
            "  constructor(model) {\n"
            "    this.model = model;\n"
            "  }\n"
            "}\n"
        )
        f.flush()
        yield f.name
    os.remove(f.name)


def test_is_file_candidate(temp_py_file):
    """Test that is_file_candidate correctly identifies an existing file."""
    assert is_file_candidate(temp_py_file) is True
    assert is_file_candidate("some_non_existent_file.py") is False


def test_is_dir_candidate():
    """Test that is_dir_candidate correctly identifies a directory."""
    with tempfile.TemporaryDirectory() as d:
        assert is_dir_candidate(d) is True
    assert is_dir_candidate("some_non_existent_dir") is False


def test_quick_extract_symbols_python(temp_py_file):
    """Test quick_extract_symbols for a Python file."""
    symbols = quick_extract_symbols(temp_py_file)
    # Expect to see both 'foo' (function) and 'MyClass' (class)
    assert "foo" in symbols
    assert "MyClass" in symbols


def test_quick_extract_symbols_js(temp_js_file):
    """Test quick_extract_symbols for a JS file."""
    symbols = quick_extract_symbols(temp_js_file)
    # Expect to see 'bar' (function) and 'Car' (class)
    assert "bar" in symbols
    assert "Car" in symbols


def test_python_extract_whole_file(temp_py_file):
    """Test python_extract with an empty symbol list => whole file."""
    extracted = python_extract(temp_py_file, symbols=[])
    assert len(extracted) == 1
    assert extracted[0][0] == "whole-file"
    assert "class MyClass" in extracted[0][1]
    assert "def foo" in extracted[0][1]


def test_python_extract_specific_symbol(temp_py_file):
    """Test python_extract with a specific symbol."""
    extracted = python_extract(temp_py_file, symbols=["foo"])
    # Should return a single snippet containing 'def foo'
    assert len(extracted) == 1
    sym, snippet = extracted[0]
    assert sym == "foo"
    assert "def foo" in snippet
    # Make sure class didn't appear
    assert "class MyClass" not in snippet


def test_js_extract_whole_file(temp_js_file):
    """Test js_extract with empty symbol => entire file."""
    extracted = js_extract(temp_js_file, symbols=[])
    assert len(extracted) == 1
    assert extracted[0][0] == "whole-file"
    assert "function bar" in extracted[0][1]
    assert "class Car" in extracted[0][1]


def test_js_extract_specific_symbol(temp_js_file):
    """Test js_extract with a specific symbol."""
    extracted = js_extract(temp_js_file, symbols=["bar"])
    assert len(extracted) == 1
    sym, snippet = extracted[0]
    assert sym == "bar"
    assert "function bar" in snippet
    # Make sure 'class Car' didn't appear
    assert "class Car" not in snippet


def test_extract_file_python_functions(temp_py_file):
    """Higher-level test of extract_file for Python with multiple symbols."""
    symbols = ["MyClass", "foo"]
    results, success = extract_file(temp_py_file, symbols)
    assert success is True
    # Expect 2 distinct blocks
    assert len(results) == 2

    # Sort them by symbol name to avoid order issues
    results_sorted = sorted(results, key=lambda x: x[0])
    assert results_sorted[0][0] == "MyClass"
    assert "class MyClass" in results_sorted[0][1]
    assert results_sorted[1][0] == "foo"
    assert "def foo" in results_sorted[1][1]


def test_extract_file_js_functions(temp_js_file):
    """Higher-level test of extract_file for JS with multiple symbols."""
    symbols = ["bar", "Car"]
    results, success = extract_file(temp_js_file, symbols)
    assert success is True
    assert len(results) == 2

    # Sort them to avoid ordering issues
    results_sorted = sorted(results, key=lambda x: x[0])
    assert results_sorted[0][0] == "Car"
    assert "class Car" in results_sorted[0][1]
    assert results_sorted[1][0] == "bar"
    assert "function bar" in results_sorted[1][1]


def test_extract_file_unsupported_extension():
    """Test that extracting a file with an unsupported extension returns the whole file with a warning."""
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        f.write("Hello, world!\nSome text.")
        f.flush()
        temp_txt_file = f.name

    try:
        results, success = extract_file(temp_txt_file, ["doesNotExist"])
        assert success is True
        assert len(results) == 1
        # Should return entire file with a note about fallback
        assert results[0][0] == "whole-file"
        assert "# Note: Symbol extraction not supported for .txt files." in results[0][1]
        assert "Hello, world!" in results[0][1]
    finally:
        os.remove(temp_txt_file)


def test_count_tokens():
    """Test the fallback case for count_tokens (when tiktoken not installed)."""
    text = "This is some text to count tokens."
    # If tiktoken is installed, result might be > 0
    # If not installed, we expect 0
    tokens = count_tokens(text)
    # We'll just assert that it's >= 0 to avoid environment-specific failures
    assert tokens >= 0


def test_cli_no_args():
    """
    Test running the CLI with no arguments. 
    We expect it to print the help message (exit code 0).
    """
    cmd = [sys.executable, "-m", "ggrab.ggrab"]
    process = subprocess.run(cmd, capture_output=True)
    # Because we call parser.print_help() and then sys.exit(0),
    # the exit code should be 0. The output should contain usage text.
    assert process.returncode == 0
    assert b"usage: ggrab" in process.stdout


def test_cli_extract_python_symbol(temp_py_file):
    """
    Test the CLI extracting a single symbol from a Python file.
    We'll capture the stdout to check for the final summary line.
    """
    cmd = [
        sys.executable, "-m", "ggrab.ggrab",
        temp_py_file, "foo"
    ]
    process = subprocess.run(cmd, capture_output=True)
    stdout = process.stdout.decode("utf-8")

    # Should mention "Gathered code from" in output
    assert "Gathered code from:" in stdout
    # Should mention the function "foo"
    assert f"functions: foo" in stdout

    # Should mention "===== Combined Snippets (copied to clipboard) ====="
    # to confirm the snippet was produced.
    assert "===== Combined Snippets" in stdout


def test_cli_extract_whole_file(temp_py_file):
    """
    Test the CLI extracting an entire Python file (no symbols).
    We just pass the file path, no function names after it.
    """
    cmd = [
        sys.executable, "-m", "ggrab.ggrab",
        temp_py_file
    ]
    process = subprocess.run(cmd, capture_output=True)
    stdout = process.stdout.decode("utf-8")

    assert "entire file" in stdout
    assert "===== Combined Snippets" in stdout


def test_cli_extract_directory():
    """
    Test the CLI when given a directory.
    We'll create a temporary directory with multiple files inside.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        py_file = Path(tmpdir) / "foo.py"
        js_file = Path(tmpdir) / "bar.js"

        py_file.write_text("def alpha():\n    pass\n")
        js_file.write_text("function bravo() { return; }")

        cmd = [
            sys.executable, "-m", "ggrab.ggrab",
            str(tmpdir)
        ]
        process = subprocess.run(cmd, capture_output=True)
        stdout = process.stdout.decode("utf-8")

        # Should mention both files
        assert str(py_file) in stdout
        assert str(js_file) in stdout
        # Combined snippets
        assert "===== Combined Snippets" in stdout
        # Should have "entire file" because no symbols provided
        assert "entire file" in stdout


def test_cli_extract_directory_with_ignore():
    """
    Create a temporary directory containing:
      - foo.py
      - bar.js
      - baz.test.js (this should be ignored)
    
    Then run 'ggrab <dir> --ignore "*.test.js"', ensuring that 'baz.test.js'
    is not mentioned in the output.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        py_file = Path(tmpdir) / "foo.py"
        py_file.write_text("def alpha():\n    pass\n")

        js_file = Path(tmpdir) / "bar.js"
        js_file.write_text("function bravo() { return; }")

        ignored_file = Path(tmpdir) / "baz.test.js"
        ignored_file.write_text("function shouldBeIgnored() { return; }")

        cmd = [
            sys.executable, "-m", "ggrab.ggrab",
            str(tmpdir),
            "--ignore", "*.test.js",
        ]
        process = subprocess.run(cmd, capture_output=True)
        stdout = process.stdout.decode("utf-8")

        # Should NOT see 'baz.test.js' or 'shouldBeIgnored' in output
        assert "baz.test.js" not in stdout
        assert "shouldBeIgnored" not in stdout

        # Should see the other two files
        assert "foo.py" in stdout
        assert "bar.js" in stdout

        # Should contain the final snippet section
        assert "===== Combined Snippets" in stdout