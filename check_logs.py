"""
Check the last N lines of output.log from remote server

This script:
1. Connects to the remote server via SSH
2. Retrieves the last N lines of XEMM_rust/output.log
3. Displays them in the terminal

Usage:
    python check_logs.py [num_lines]

    Default: 100 lines
    Example: python check_logs.py 200
"""

import os
import sys
import subprocess
import platform

# Configuration (from deploy.py)
REMOTE_USER = "ubuntu"
REMOTE_HOST = "54.95.246.213"
REMOTE_PATH = "/home/ubuntu/XEMM_rust"
LOG_FILE = "output.log"
SSH_KEY_NAME = "lighter.pem"  # SSH key filename
DEFAULT_NUM_LINES = 100


def find_ssh_key():
    """Find SSH key in Windows or WSL filesystem."""
    possible_paths = [
        os.path.expanduser(f"~/{SSH_KEY_NAME}"),  # WSL/Linux home directory
        f"./{SSH_KEY_NAME}",  # Current directory (Windows native)
        os.path.join(os.getcwd(), SSH_KEY_NAME),  # Absolute current dir
        SSH_KEY_NAME,  # Relative path
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return os.path.abspath(path)

    return None


SSH_KEY = find_ssh_key()


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(text.center(70))
    print("=" * 70 + "\n")


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
        print(f"  - ~/{SSH_KEY_NAME} (WSL/Linux home)")
        print(f"  - ./{SSH_KEY_NAME} (current directory)")
        return False

    print_success(f"Found SSH key: {SSH_KEY}")

    # Set proper permissions (Unix-like systems only)
    if platform.system() != "Windows":
        try:
            os.chmod(SSH_KEY, 0o600)
            print_success("SSH key permissions set to 600")
        except Exception as e:
            print_info(f"Could not set SSH key permissions: {e}")

    return True


def check_remote_logs(num_lines):
    """Retrieve and display the last N lines of output.log from remote server."""
    print_info(f"Fetching last {num_lines} lines from {LOG_FILE}...")

    cmd = [
        "ssh",
        "-i", SSH_KEY,
        "-o", "ConnectTimeout=30",
        "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        f"cd {REMOTE_PATH} && tail -n {num_lines} {LOG_FILE}"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding='utf-8',
            errors='replace',  # Replace invalid characters instead of failing
            timeout=30
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            if not output:
                print_info("Log file is empty or does not exist")
                return False

            print_header(f"Last {num_lines} lines of {LOG_FILE}")
            print(output)
            print("\n" + "=" * 70)

            # Count actual lines returned
            line_count = len(output.split('\n'))
            print_info(f"Displayed {line_count} lines")
            return True
        else:
            print_error(f"Failed to read remote log file: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print_error("SSH command timed out")
        return False
    except Exception as e:
        print_error(f"Error fetching logs: {e}")
        return False


def main():
    """Main function."""
    # Parse command line arguments
    num_lines = DEFAULT_NUM_LINES
    if len(sys.argv) > 1:
        try:
            num_lines = int(sys.argv[1])
            if num_lines <= 0:
                print_error("Number of lines must be positive")
                sys.exit(1)
        except ValueError:
            print_error(f"Invalid number: {sys.argv[1]}")
            print(f"Usage: python {sys.argv[0]} [num_lines]")
            sys.exit(1)

    print_header("XEMM Remote Log Checker")
    print_info(f"Remote: {REMOTE_USER}@{REMOTE_HOST}:{REMOTE_PATH}/{LOG_FILE}")
    print_info(f"Lines to fetch: {num_lines}")

    # Step 1: Check SSH key
    if not check_ssh_key():
        sys.exit(1)

    # Step 2: Fetch and display logs
    if not check_remote_logs(num_lines):
        sys.exit(1)

    print_success("Log check complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
