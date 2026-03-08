"""GitHub Copilot device-flow OAuth authentication.

Implements the same device-flow login used by github.com/github/copilot.vim and
the GitHub CLI, giving users a browser-based login experience instead of having
to paste a token manually.

Flow:
    1. POST /login/device/code  → get device_code + user_code
    2. Show user_code + verification_uri to the user (open browser)
    3. Poll /login/oauth/access_token until user approves
    4. Exchange GitHub OAuth token for a short-lived Copilot API token
    5. Store the GitHub token in .env for future auto-refresh

Copilot tokens expire every ~30 minutes; a fresh one is obtained automatically
on each session start using the stored GitHub token.
"""

from __future__ import annotations

import os
import time
import logging
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Constants mirroring the ones used by copilot.vim / GitHub CLI
# -----------------------------------------------------------------------
GITHUB_CLIENT_ID = "Iv1.b507a08c87ecfe98"   # public Copilot OAuth App id
DEVICE_CODE_URL  = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
OAUTH_SCOPE = "read:user"

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


# -----------------------------------------------------------------------
# Device-flow helpers
# -----------------------------------------------------------------------

def request_device_code() -> dict:
    """POST to GitHub to start the device flow.

    Returns:
        Dict with device_code, user_code, verification_uri, expires_in, interval
    """
    resp = requests.post(
        DEVICE_CODE_URL,
        headers={"Accept": "application/json"},
        data={"client_id": GITHUB_CLIENT_ID, "scope": OAUTH_SCOPE},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def poll_for_token(device_code: str, interval: int = 5, expires_in: int = 900) -> str:
    """Poll GitHub until the user approves the device in their browser.

    Args:
        device_code: Code from request_device_code().
        interval:    Polling interval in seconds (from GitHub response).
        expires_in:  Token lifetime in seconds.

    Returns:
        GitHub OAuth access_token string.

    Raises:
        TimeoutError: If the user doesn't approve in time.
        RuntimeError: If GitHub returns an unexpected error.
    """
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        resp = requests.post(
            ACCESS_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if "access_token" in data:
            return data["access_token"]

        error = data.get("error", "")
        if error == "authorization_pending":
            continue
        elif error == "slow_down":
            interval += 5
        elif error == "expired_token":
            raise TimeoutError("Device code expired. Please run login again.")
        elif error == "access_denied":
            raise RuntimeError("User denied access.")
        else:
            raise RuntimeError(f"GitHub auth error: {error}")

    raise TimeoutError("Login timed out. Please run login again.")


def get_copilot_token(github_token: str) -> Tuple[str, int]:
    """Exchange a GitHub OAuth token for a short-lived Copilot API token.

    Args:
        github_token: GitHub personal access token (or OAuth token).

    Returns:
        Tuple of (copilot_token_string, refresh_in_seconds).

    Raises:
        requests.HTTPError: If the exchange fails (e.g. no Copilot subscription).
    """
    resp = requests.get(
        COPILOT_TOKEN_URL,
        headers={
            "Authorization": f"token {github_token}",
            "Accept": "application/json",
            "Editor-Version": "vscode/1.90.0",
            "Copilot-Integration-Id": "studytipsengine",
        },
        timeout=15,
    )
    if resp.status_code == 403:
        raise RuntimeError(
            "GitHub account does not have an active Copilot subscription. "
            "Visit https://github.com/features/copilot to activate one."
        )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("token", "")
    refresh_in = int(data.get("refresh_in", 1800))
    return token, refresh_in


# -----------------------------------------------------------------------
# Persistence helpers
# -----------------------------------------------------------------------

def save_github_token_to_env(github_token: str) -> None:
    """Write / update GITHUB_COPILOT_TOKEN in the .env file.

    Args:
        github_token: GitHub OAuth token to persist.
    """
    os.environ["GITHUB_COPILOT_TOKEN"] = github_token

    if not ENV_FILE.exists():
        ENV_FILE.write_text(f"GITHUB_COPILOT_TOKEN={github_token}\n")
        return

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    found = False
    new_lines = []
    for line in lines:
        if line.startswith("GITHUB_COPILOT_TOKEN="):
            new_lines.append(f"GITHUB_COPILOT_TOKEN={github_token}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"GITHUB_COPILOT_TOKEN={github_token}\n")

    ENV_FILE.write_text("".join(new_lines), encoding="utf-8")
    logger.info("GITHUB_COPILOT_TOKEN saved to .env")


# -----------------------------------------------------------------------
# High-level token manager (used by CopilotClient)
# -----------------------------------------------------------------------

class CopilotTokenManager:
    """Manages GitHub Copilot token lifecycle (refresh, cache).

    Automatically refreshes the short-lived Copilot token when it nears
    expiry, using the stored GitHub OAuth token.
    """

    def __init__(self) -> None:
        self._copilot_token: Optional[str] = None
        self._expires_at: float = 0.0

    def get_token(self) -> Optional[str]:
        """Return a valid Copilot API token, refreshing if needed.

        Returns:
            Copilot token string, or None if no GitHub token is configured.
        """
        # Refresh if expired or nearly expired (60 s buffer)
        if self._copilot_token and time.time() < self._expires_at - 60:
            return self._copilot_token

        github_token = os.environ.get("GITHUB_COPILOT_TOKEN", "")
        if not github_token:
            return None

        try:
            copilot_token, refresh_in = get_copilot_token(github_token)
            self._copilot_token = copilot_token
            self._expires_at = time.time() + refresh_in
            logger.debug("Copilot token refreshed, valid for %ds", refresh_in)
            return self._copilot_token
        except Exception as exc:
            logger.warning("Could not refresh Copilot token: %s", exc)
            return None

    def invalidate(self) -> None:
        """Force token refresh on next call."""
        self._copilot_token = None
        self._expires_at = 0.0


# Singleton reused across the process
_token_manager = CopilotTokenManager()


def get_token() -> Optional[str]:
    """Module-level shortcut to get a valid Copilot token."""
    return _token_manager.get_token()


def list_copilot_models(github_token: str) -> list:
    """Fetch all models available to this Copilot account from the API.

    Returns only chat-completion-capable models with model_picker_enabled=True
    (the same set VS Code shows in its model picker).

    Args:
        github_token: GitHub OAuth token stored in .env

    Returns:
        List of dicts: {id, name, vendor, category, context_window, max_output,
                        supports_vision, preview}
    """
    copilot_token, _ = get_copilot_token(github_token)
    resp = requests.get(
        "https://api.githubcopilot.com/models",
        headers={
            "Authorization": f"Bearer {copilot_token}",
            "Accept": "application/json",
            "Editor-Version": "vscode/1.90.0",
        },
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json().get("data", [])

    results = []
    for m in raw:
        caps = m.get("capabilities", {})
        # Skip non-chat models (embeddings etc.)
        if caps.get("type") != "chat":
            continue
        # Skip models not shown in the VS Code model picker
        if not m.get("model_picker_enabled", False):
            continue
        endpoints = m.get("supported_endpoints", [])
        # Skip models that only support /responses or /v1/messages (not chat completions)
        if endpoints and "/chat/completions" not in endpoints:
            continue
        results.append({
            "id": m["id"],
            "name": m.get("name", m["id"]),
            "vendor": m.get("vendor", "Unknown"),
            "category": m.get("model_picker_category", "versatile"),
            "picker_enabled": True,
            "preview": m.get("preview", False),
            "context_window": caps.get("limits", {}).get("max_context_window_tokens", 8192),
            "max_output": caps.get("limits", {}).get("max_output_tokens", 4096),
            "supports_vision": "vision" in caps.get("supports", {}),
        })
    return results


def is_real_github_token(token: str) -> bool:
    """Return True if token looks like a genuine GitHub OAuth/PAT token.

    Rejects obvious placeholders like 'your_github_copilot_token'.
    """
    if not token:
        return False
    prefixes = ("ghu_", "ghp_", "gho_", "github_pat_", "ghs_")
    return any(token.startswith(p) for p in prefixes)


# -----------------------------------------------------------------------
# Interactive CLI login (blocking, prints to stdout)
# -----------------------------------------------------------------------

def interactive_login(open_browser: bool = True) -> str:
    """Run the full device-flow login and return the GitHub OAuth token.

    Intended for CLI usage. Prints prompts to stdout.

    Args:
        open_browser: Automatically open the verification URL in the browser.

    Returns:
        GitHub OAuth token string.
    """
    print("🔑 Starting GitHub Copilot device authentication…")
    data = request_device_code()

    user_code = data["user_code"]
    verification_uri = data["verification_uri"]
    expires_in = int(data.get("expires_in", 900))
    interval = int(data.get("interval", 5))

    print(f"\n  1. Visit:  {verification_uri}")
    print(f"  2. Enter code: {user_code}\n")

    if open_browser:
        webbrowser.open(verification_uri)

    print("  Waiting for authorisation…  (press Ctrl+C to cancel)\n")
    github_token = poll_for_token(data["device_code"], interval=interval, expires_in=expires_in)

    # Verify Copilot access
    get_copilot_token(github_token)  # raises if no subscription

    save_github_token_to_env(github_token)
    _token_manager.invalidate()

    print("✅ GitHub Copilot connected successfully!")
    return github_token
