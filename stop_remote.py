#!/usr/bin/env python3
"""
Stop the XEMM trading bot on the remote server.
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

# Remote server configuration
REMOTE_USER = "ubuntu"
REMOTE_HOST = "54.95.246.213"
REMOTE_PATH = "/home/ubuntu/XEMM_rust"
SSH_KEY_NAME = "lighter.pem"

# Find SSH key in possible locations
HOME_DIR = Path.home()
SSH_KEY_PATHS = [
    HOME_DIR / SSH_KEY_NAME,
    Path.cwd() / SSH_KEY_NAME,
    Path.cwd().parent / SSH_KEY_NAME,
]

SSH_KEY = None
for key_path in SSH_KEY_PATHS:
    if key_path.exists():
        SSH_KEY = str(key_path)
        break


def print_header(text):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}")


def print_success(text):
    """Print success message."""
    print(f"[OK] {text}")


def print_error(text):
    """Print error message."""
    print(f"[ERROR] {text}")


def print_info(text):
    """Print info message."""
    print(f"[INFO] {text}")


def check_ssh_key():
    """Check if SSH key exists."""
    if SSH_KEY is None:
        print_error(f"SSH key '{SSH_KEY_NAME}' not found in any expected location")
        print("Searched locations:")
        print(f"  - ~/{SSH_KEY_NAME} (home directory)")
        print(f"  - ./{SSH_KEY_NAME} (current directory)")
        return False

    print_success(f"Found SSH key: {SSH_KEY}")
    return True


def stop_remote_bot():
    """Stop the bot on the remote server."""
    print_header("Stopping Remote Bot")
    
    if not check_ssh_key():
        return False

    print_info(f"Stopping bot on {REMOTE_USER}@{REMOTE_HOST}...")

    # Remote commands to stop the bot
    remote_cmd = (
        "pkill -f 'run_bot_loop_cargo.sh' || true; "
        "pkill -f 'cargo run.*xemm' || true; "
        "pkill -f 'xemm_rust' || true; "
        "killall xemm_rust 2>/dev/null || true; "
        "echo 'Stop commands executed'"
    )

    cmd = [
        "ssh",
        "-i", SSH_KEY,
        "-o", "ConnectTimeout=30",
        "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        remote_cmd
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print_success("Bot stopped successfully")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print_error(f"Stop command failed with return code {result.returncode}")
            if result.stderr:
                print(f"Error output: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print_error("SSH command timed out")
        return False
    except Exception as e:
        print_error(f"Failed to stop bot: {e}")
        return False


if __name__ == "__main__":
    try:
        success = stop_remote_bot()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
        sys.exit(1)
