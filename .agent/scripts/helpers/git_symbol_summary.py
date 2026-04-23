#!/usr/bin/env python
"""
Summarize changed symbols between Git refs.

Compares Python files between a base ref (default: merge-base with main, fallback: HEAD~1)
and the current HEAD, extracting and reporting changed function/class signatures.

Output is opaque (non-Python files reported as binary) by default; use --python-only
to report only Python symbol changes.

Example:
    python git_symbol_summary.py
    python git_symbol_summary.py --base-ref main
    python git_symbol_summary.py --python-only --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Import shared AST utilities
try:
    from _ast_utils import extract_signatures
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from _ast_utils import extract_signatures


def run_git_command(cmd: list[str], cwd: str | None = None) -> tuple[str, str, int]:
    """Run a git command and return stdout, stderr, and return code."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return '', 'Command timed out', 1
    except Exception as e:
        return '', str(e), 1


def get_base_ref(cwd: str | None = None) -> str:
    """Determine base ref: merge-base with main, fallback to HEAD~1."""
    # Try merge-base with main
    stdout, stderr, rc = run_git_command(['git', 'merge-base', 'HEAD', 'main'], cwd=cwd)
    if rc == 0 and stdout:
        return stdout
    
    # Fallback: HEAD~1
    stdout, stderr, rc = run_git_command(['git', 'rev-parse', 'HEAD~1'], cwd=cwd)
    if rc == 0 and stdout:
        return stdout
    
    return 'HEAD'


def get_changed_files(base_ref: str, cwd: str | None = None) -> list[str]:
    """Get list of changed files between base_ref and HEAD."""
    stdout, stderr, rc = run_git_command(
        ['git', 'diff', '--name-only', base_ref, 'HEAD'],
        cwd=cwd
    )
    if rc != 0:
        return []
    
    return [f for f in stdout.split('\n') if f]


def get_file_at_ref(file_path: str, ref: str, cwd: str | None = None) -> str | None:
    """Get content of file at specific git ref."""
    stdout, stderr, rc = run_git_command(
        ['git', 'show', f'{ref}:{file_path}'],
        cwd=cwd
    )
    if rc != 0:
        return None
    return stdout


def is_python_file(file_path: str) -> bool:
    """Check if file is a Python file."""
    return file_path.endswith('.py')


def extract_signatures_from_content(content: str, module_name: str) -> list[dict[str, Any]]:
    """Parse content string and extract signatures."""
    try:
        tree = __import__('ast').parse(content, filename=module_name)
        return extract_signatures(tree, module_name)
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(
        description='Summarize changed symbols between Git refs.'
    )
    parser.add_argument(
        '--base-ref',
        default=None,
        help='Base ref for comparison (default: merge-base with main, fallback: HEAD~1).'
    )
    parser.add_argument(
        '--python-only',
        action='store_true',
        help='Report only Python file changes; skip non-Python files.'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON instead of plain text.'
    )
    parser.add_argument(
        '--cwd',
        default=None,
        help='Working directory for git commands (default: current directory).'
    )
    
    args = parser.parse_args()
    
    cwd = args.cwd or None
    base_ref = args.base_ref or get_base_ref(cwd)
    changed_files = get_changed_files(base_ref, cwd)
    
    results: list[dict[str, Any]] = []
    
    for file_path in changed_files:
        if args.python_only and not is_python_file(file_path):
            continue
        
        if not is_python_file(file_path):
            # Non-Python file; report as opaque
            results.append({
                'file': file_path,
                'type': 'binary',
                'signatures_before': [],
                'signatures_after': [],
            })
            continue
        
        # Python file; extract signatures before and after
        content_before = get_file_at_ref(file_path, base_ref, cwd)
        content_after = get_file_at_ref(file_path, 'HEAD', cwd)
        
        sigs_before = []
        sigs_after = []
        
        if content_before:
            sigs_before = extract_signatures_from_content(content_before, file_path)
        
        if content_after:
            sigs_after = extract_signatures_from_content(content_after, file_path)
        
        results.append({
            'file': file_path,
            'type': 'python',
            'signatures_before': sigs_before,
            'signatures_after': sigs_after,
        })
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Base ref: {base_ref}")
        print(f"Changed files: {len(changed_files)}")
        print()
        
        for entry in results:
            print(f"{entry['file']} ({entry['type']})")
            
            if entry['type'] == 'binary':
                print("  (non-Python file)")
            else:
                before_names = {s['qualified_name'] for s in entry['signatures_before']}
                after_names = {s['qualified_name'] for s in entry['signatures_after']}
                
                added = after_names - before_names
                removed = before_names - after_names
                
                if added:
                    print(f"  Added: {', '.join(sorted(added))}")
                if removed:
                    print(f"  Removed: {', '.join(sorted(removed))}")
                if not added and not removed:
                    print("  (no symbol changes detected)")
            print()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
