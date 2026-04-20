"""
GitHub API client utility with authentication resolution and pagination support.

Provides:
- Auth resolution: GH_TOKEN environment variable first, then `gh auth` CLI fallback
- Paginated GET wrapper with rate-limit-aware error envelope
- Deterministic error messages for auth, rate-limit, and network failures
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Generator
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class GitHubAuthError(Exception):
    """Raised when GitHub authentication fails or is unavailable."""
    pass


class GitHubRateLimitError(Exception):
    """Raised when GitHub rate limit is exceeded."""
    pass


class GitHubAPIError(Exception):
    """Raised for other GitHub API errors."""
    pass


def resolve_github_token() -> str:
    """
    Resolve GitHub auth token.
    
    Priority:
    1. GH_TOKEN environment variable
    2. gh CLI auth token (via `gh auth token`)
    
    Returns:
        Auth token string.
    
    Raises:
        GitHubAuthError: If no auth method is available.
    """
    # Try environment variable first
    token = os.environ.get('GH_TOKEN')
    if token:
        return token
    
    # Try gh CLI
    try:
        result = subprocess.run(
            ['gh', 'auth', 'token'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    raise GitHubAuthError(
        'No GitHub auth token available. '
        'Set GH_TOKEN environment variable or run `gh auth login`.'
    )


def get_github_api(
    endpoint: str,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Make a single GET request to GitHub API.
    
    Args:
        endpoint: API endpoint (e.g., '/repos/owner/repo/issues').
        token: GitHub auth token. If None, resolved automatically.
        headers: Additional headers to include.
    
    Returns:
        Parsed JSON response.
    
    Raises:
        GitHubAuthError: If auth fails.
        GitHubRateLimitError: If rate limited.
        GitHubAPIError: For other API errors.
    """
    if token is None:
        token = resolve_github_token()
    
    url = f'https://api.github.com{endpoint}'
    
    req_headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'quantmap-agent',
    }
    if headers:
        req_headers.update(headers)
    
    try:
        req = Request(url, headers=req_headers, method='GET')
        with urlopen(req, timeout=10) as response:
            data = response.read().decode('utf-8')
            return json.loads(data)
    except HTTPError as e:
        if e.code == 401:
            raise GitHubAuthError(f'Authentication failed: {e.reason}')
        elif e.code == 403:
            # Check for rate limit
            if 'rate limit' in e.read().decode('utf-8').lower():
                raise GitHubRateLimitError('GitHub API rate limit exceeded.')
            raise GitHubAPIError(f'Forbidden (403): {e.reason}')
        elif e.code == 404:
            raise GitHubAPIError(f'Not found (404): {e.reason}')
        else:
            raise GitHubAPIError(f'HTTP error {e.code}: {e.reason}')
    except URLError as e:
        raise GitHubAPIError(f'Network error: {e.reason}')
    except json.JSONDecodeError as e:
        raise GitHubAPIError(f'Invalid JSON response: {e}')
    except Exception as e:
        raise GitHubAPIError(f'Request failed: {e}')


def paginate_github_api(
    endpoint: str,
    token: str | None = None,
    per_page: int = 30,
    max_pages: int | None = None,
    headers: dict[str, str] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Paginate through GitHub API results.
    
    Args:
        endpoint: Base API endpoint.
        token: GitHub auth token. If None, resolved automatically.
        per_page: Results per page (1-100).
        max_pages: Maximum pages to fetch (None = unlimited).
        headers: Additional headers to include.
    
    Yields:
        Individual items from paginated results.
    
    Raises:
        GitHubAuthError: If auth fails.
        GitHubRateLimitError: If rate limited.
        GitHubAPIError: For other API errors.
    """
    if token is None:
        token = resolve_github_token()
    
    per_page = min(100, max(1, per_page))
    page = 1
    pages_fetched = 0
    
    while True:
        if max_pages and pages_fetched >= max_pages:
            break
        
        # Build paginated endpoint
        separator = '&' if '?' in endpoint else '?'
        paginated_endpoint = f'{endpoint}{separator}page={page}&per_page={per_page}'
        
        try:
            response = get_github_api(paginated_endpoint, token, headers)
        except GitHubAPIError:
            # If not a list response, just yield the single response and stop
            if isinstance(response, dict) and 'message' not in response:
                yield response
            break
        
        # Handle both list and dict responses
        if isinstance(response, list):
            if not response:
                break  # No more results
            
            for item in response:
                yield item
            
            pages_fetched += 1
            page += 1
        else:
            # Single object response, not paginated
            yield response
            break
