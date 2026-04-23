#!/usr/bin/env python
"""
Dump Python function and class signatures from one or more files.

Outputs signatures in plain text by default, or as JSON with --json flag.
Handles parse errors gracefully and reports them inline.

Example:
    python signature_dump.py src/my_module.py
    python signature_dump.py src/*.py --json
    python signature_dump.py src/ --json > signatures.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Import shared AST utilities
try:
    from _ast_utils import parse_python_file, extract_signatures
except ImportError:
    # Fallback for different import paths
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from _ast_utils import parse_python_file, extract_signatures


def format_signature_plain(sig: dict[str, Any], file_path: str | None = None) -> str:
    """Format a single signature as plain text."""
    prefix = f"{file_path}:{sig['lineno']}  " if file_path else ""
    
    if sig['type'] == 'class':
        return f"{prefix}class {sig['qualified_name']}"
    
    elif sig['type'] in ('function', 'async_function'):
        async_prefix = 'async ' if sig['type'] == 'async_function' else ''
        args_str = ', '.join(sig.get('args', []))
        return f"{prefix}{async_prefix}def {sig['qualified_name']}({args_str})"
    
    return f"{prefix}{sig['type']} {sig['qualified_name']}"


def main():
    parser = argparse.ArgumentParser(
        description='Dump Python function and class signatures from files.'
    )
    parser.add_argument(
        'paths',
        nargs='+',
        help='Python files or directories to analyze.'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON instead of plain text.'
    )
    parser.add_argument(
        '--include-decorators',
        action='store_true',
        help='Include decorator information in output.'
    )
    parser.add_argument(
        '--include-docstrings',
        action='store_true',
        help='Include first line of docstrings in output.'
    )
    
    args = parser.parse_args()
    
    results: dict[str, Any] | list[Any] = {} if args.json else []
    
    for path_arg in args.paths:
        path = Path(path_arg)
        
        if path.is_dir():
            # Recursively find all .py files
            py_files = sorted(path.glob('**/*.py'))
        elif path.is_file():
            py_files = [path]
        else:
            # Try glob pattern
            py_files = sorted(Path('.').glob(path_arg))
        
        for py_file in py_files:
            if not py_file.suffix == '.py':
                continue
            
            parse_result = parse_python_file(py_file)
            file_path_str = str(py_file)
            
            if parse_result['error']:
                entry = {
                    'file': file_path_str,
                    'error': parse_result['error'],
                    'signatures': []
                }
                if args.json:
                    if isinstance(results, dict):
                        results[file_path_str] = entry
                    else:
                        results.append(entry)
                else:
                    print(f"{file_path_str}: ERROR: {parse_result['error']}", file=sys.stderr)
                continue
            
            sigs = extract_signatures(
                parse_result['ast'],
                module_name=py_file.stem,
                include_decorators=args.include_decorators,
            )
            
            if args.json:
                # JSON output
                sig_list = []
                for sig in sigs:
                    sig_copy = sig.copy()
                    if not args.include_docstrings:
                        sig_copy.pop('docstring_first_line', None)
                    sig_list.append(sig_copy)
                
                entry = {
                    'file': file_path_str,
                    'error': None,
                    'signatures': sig_list
                }
                if isinstance(results, dict):
                    results[file_path_str] = entry
                else:
                    results.append(entry)
            else:
                # Plain text output
                if sigs:
                    print(f"\n{file_path_str}:")
                    for sig in sigs:
                        line = format_signature_plain(sig)
                        if args.include_docstrings and sig.get('docstring_first_line'):
                            line += f"  # {sig['docstring_first_line']}"
                        print(f"  {line}")
                else:
                    print(f"{file_path_str}: (no signatures)")
    
    if args.json:
        print(json.dumps(results, indent=2))
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
