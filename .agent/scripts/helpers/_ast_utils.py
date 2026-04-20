"""
Shared AST utilities for Python signature extraction and analysis.

Provides low-level AST parsing, signature extraction, qualified-name building,
docstring extraction, and optional decorator inspection.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def safe_read_text(path: Path | str) -> str | None:
    """
    Safely read a text file.
    
    Args:
        path: File path.
    
    Returns:
        File contents as string, or None if read fails.
    """
    try:
        return Path(path).read_text(encoding='utf-8')
    except Exception:
        return None


def parse_python_file(path: Path | str) -> dict[str, Any]:
    """
    Parse a Python file and return AST or error.
    
    Args:
        path: File path to parse.
    
    Returns:
        Dict with keys:
        - 'ast': Parsed AST module (or None if parse fails)
        - 'source': File source code (or empty string if read fails)
        - 'error': Error message (or None if successful)
    """
    path = Path(path)
    source = safe_read_text(path)
    
    if source is None:
        return {'ast': None, 'source': '', 'error': f'Could not read file: {path}'}
    
    try:
        tree = ast.parse(source, filename=str(path))
        return {'ast': tree, 'source': source, 'error': None}
    except SyntaxError as e:
        return {'ast': None, 'source': source, 'error': f'Syntax error: {e}'}
    except Exception as e:
        return {'ast': None, 'source': source, 'error': f'Parse error: {e}'}


def get_qualified_name(
    node: ast.AST | str,
    parent_stack: list[str] | None = None,
) -> str:
    """
    Build a qualified name for a node in scope hierarchy.
    
    Args:
        node: AST node (FunctionDef, AsyncFunctionDef, ClassDef) or already-computed name string.
        parent_stack: List of enclosing class/function names for nesting context.
    
    Returns:
        Qualified name, e.g. 'ClassName.method_name' or 'outer_func.<locals>.inner_func'.
    """
    if isinstance(node, str):
        node_name = node
    elif hasattr(node, 'name'):
        node_name = node.name
    else:
        node_name = '<unknown>'
    
    if not parent_stack:
        return node_name
    
    return '.'.join(parent_stack + [node_name])


def extract_docstring_first_line(docstring: str | None) -> str | None:
    """
    Extract first line of a docstring.
    
    Args:
        docstring: Docstring (or None).
    
    Returns:
        First non-empty line, or None if empty/missing.
    """
    if not docstring:
        return None
    
    lines = docstring.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def extract_signatures(
    ast_module: ast.Module,
    module_name: str = '<module>',
    include_decorators: bool = False,
    parent_stack: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Extract function and class signatures from an AST module.
    
    Args:
        ast_module: Parsed AST module.
        module_name: Name of the module (for qualified names).
        include_decorators: Whether to include decorator info.
        parent_stack: Internal use for tracking class/function nesting.
    
    Returns:
        List of signature dicts with keys:
        - 'type': 'class' | 'function' | 'async_function'
        - 'name': Function/class name
        - 'qualified_name': Fully qualified name with nesting
        - 'lineno': Line number in source
        - 'docstring_first_line': First line of docstring (or None)
        - 'decorators': List of decorator names (if include_decorators=True)
        - 'args': List of argument names (functions only)
        - 'async': Whether function is async (functions only)
    """
    if parent_stack is None:
        parent_stack = []
    
    signatures = []
    
    for node in ast.walk(ast_module):
        if isinstance(node, ast.ClassDef):
            qualified = get_qualified_name(node, parent_stack)
            docstring = ast.get_docstring(node)
            decorators = [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list] if include_decorators else []
            
            signatures.append({
                'type': 'class',
                'name': node.name,
                'qualified_name': qualified,
                'lineno': node.lineno,
                'docstring_first_line': extract_docstring_first_line(docstring),
                'decorators': decorators,
            })
            
            # Recursively extract nested functions/classes
            nested_stack = parent_stack + [node.name]
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    nested = extract_signatures(
                        ast.Module(body=[child]),
                        module_name,
                        include_decorators,
                        nested_stack,
                    )
                    signatures.extend(nested)
        
        elif isinstance(node, ast.FunctionDef):
            qualified = get_qualified_name(node, parent_stack)
            docstring = ast.get_docstring(node)
            decorators = [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list] if include_decorators else []
            args = [arg.arg for arg in node.args.args]
            
            signatures.append({
                'type': 'function',
                'name': node.name,
                'qualified_name': qualified,
                'lineno': node.lineno,
                'docstring_first_line': extract_docstring_first_line(docstring),
                'decorators': decorators,
                'args': args,
                'async': False,
            })
        
        elif isinstance(node, ast.AsyncFunctionDef):
            qualified = get_qualified_name(node, parent_stack)
            docstring = ast.get_docstring(node)
            decorators = [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list] if include_decorators else []
            args = [arg.arg for arg in node.args.args]
            
            signatures.append({
                'type': 'async_function',
                'name': node.name,
                'qualified_name': qualified,
                'lineno': node.lineno,
                'docstring_first_line': extract_docstring_first_line(docstring),
                'decorators': decorators,
                'args': args,
                'async': True,
            })
    
    # Remove duplicates (ast.walk visits nested nodes; we want only top-level module walk)
    if parent_stack:  # Only apply this logic for recursive calls
        return signatures
    
    # For the module level, deduplicate by (name, lineno) to avoid double-counting from ast.walk
    seen = set()
    unique = []
    for sig in signatures:
        key = (sig['qualified_name'], sig['lineno'])
        if key not in seen:
            seen.add(key)
            unique.append(sig)
    
    return sorted(unique, key=lambda s: s['lineno'])
