"""
Download and analyze trade CSV files from remote server

This script:
1. Connects to the remote server via SSH
2. Automatically detects all *_trades.csv files
3. Downloads them to a local directory
4. Displays comprehensive statistics summary

Usage:
    python download_trades.py
"""

import os
import sys
import subprocess
import platform
from pathlib import Path
import csv
from datetime import datetime
from collections import defaultdict
import statistics

# Configuration (from deploy.py)
REMOTE_USER = "ubuntu"
REMOTE_HOST = "54.95.246.213"
REMOTE_PATH = "/home/ubuntu/XEMM_rust"
LOCAL_DOWNLOAD_DIR = "downloaded_trades"
SSH_KEY_NAME = "lighter.pem"  # SSH key filename


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


def discover_csv_files():
    """Discover all *_trades.csv files on remote server."""
    print_info("Discovering CSV files on remote server...")

    cmd = [
        "ssh",
        "-i", SSH_KEY,
        "-o", "ConnectTimeout=30",
        "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        f"cd {REMOTE_PATH} && ls *_trades.csv 2>/dev/null || echo 'NO_FILES'"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            if output == "NO_FILES" or not output:
                print_info("No *_trades.csv files found on remote server")
                return []

            files = [f.strip() for f in output.split('\n') if f.strip()]
            print_success(f"Found {len(files)} CSV file(s): {', '.join(files)}")
            return files
        else:
            print_error(f"Failed to list remote files: {result.stderr}")
            return []

    except subprocess.TimeoutExpired:
        print_error("SSH command timed out")
        return []
    except Exception as e:
        print_error(f"Error discovering CSV files: {e}")
        return []


def download_csv_files(csv_files):
    """Download CSV files from remote server."""
    if not csv_files:
        return []

    # Create local download directory
    os.makedirs(LOCAL_DOWNLOAD_DIR, exist_ok=True)
    print_success(f"Created download directory: {LOCAL_DOWNLOAD_DIR}")

    downloaded_files = []

    for csv_file in csv_files:
        print_info(f"Downloading {csv_file}...")

        remote_file_path = f"{REMOTE_PATH}/{csv_file}"
        local_file_path = os.path.join(LOCAL_DOWNLOAD_DIR, csv_file)

        cmd = [
            "scp",
            "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=30",
            f"{REMOTE_USER}@{REMOTE_HOST}:{remote_file_path}",
            local_file_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                file_size = os.path.getsize(local_file_path)
                print_success(f"Downloaded {csv_file} ({file_size} bytes)")
                downloaded_files.append(local_file_path)
            else:
                print_error(f"Failed to download {csv_file}: {result.stderr}")

        except subprocess.TimeoutExpired:
            print_error(f"Download of {csv_file} timed out")
        except Exception as e:
            print_error(f"Error downloading {csv_file}: {e}")

    return downloaded_files


def parse_csv_file(file_path):
    """Parse a CSV file and return list of trade records."""
    trades = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip duplicate header rows (bug in CSV logger)
                if row.get('timestamp') == 'timestamp' or row.get('latency_ms') == 'latency_ms':
                    continue

                # Convert numeric fields
                try:
                    trade = {
                        'timestamp': row['timestamp'],
                        'latency_ms': float(row['latency_ms']),
                        'symbol': row['symbol'],
                        'pacifica_side': row['pacifica_side'],
                        'hyperliquid_side': row['hyperliquid_side'],
                        'pacifica_price': float(row['pacifica_price']),
                        'pacifica_size': float(row['pacifica_size']),
                        'pacifica_notional': float(row['pacifica_notional']),
                        'pacifica_fee': float(row['pacifica_fee']),
                        'hyperliquid_price': float(row['hyperliquid_price']),
                        'hyperliquid_size': float(row['hyperliquid_size']),
                        'hyperliquid_notional': float(row['hyperliquid_notional']),
                        'hyperliquid_fee': float(row['hyperliquid_fee']),
                        'total_fees': float(row['total_fees']),
                        'expected_profit_bps': float(row['expected_profit_bps']),
                        'actual_profit_bps': float(row['actual_profit_bps']),
                        'actual_profit_usd': float(row['actual_profit_usd']),
                        'gross_pnl': float(row['gross_pnl']),
                    }
                    trades.append(trade)
                except (ValueError, KeyError) as e:
                    print_error(f"Error parsing row in {file_path}: {e}")
                    continue

        return trades

    except Exception as e:
        print_error(f"Error reading {file_path}: {e}")
        return []


def display_stats(all_trades):
    """Display comprehensive statistics summary."""
    if not all_trades:
        print_info("No trades to analyze")
        return

    print_header("TRADE STATISTICS SUMMARY")

    # Group trades by symbol
    trades_by_symbol = defaultdict(list)
    for trade in all_trades:
        trades_by_symbol[trade['symbol']].append(trade)

    # Overall statistics
    total_trades = len(all_trades)
    total_profit_usd = sum(t['actual_profit_usd'] for t in all_trades)
    total_fees = sum(t['total_fees'] for t in all_trades)
    avg_profit_usd = total_profit_usd / total_trades if total_trades > 0 else 0
    profitable_trades = sum(1 for t in all_trades if t['actual_profit_usd'] > 0)
    win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0

    # Latency stats
    latencies = [t['latency_ms'] for t in all_trades]
    avg_latency = statistics.mean(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    median_latency = statistics.median(latencies) if latencies else 0

    # Profit stats
    profits = [t['actual_profit_usd'] for t in all_trades]
    max_profit = max(profits) if profits else 0
    min_profit = min(profits) if profits else 0

    # BPS stats
    avg_expected_bps = statistics.mean([t['expected_profit_bps'] for t in all_trades]) if all_trades else 0
    avg_actual_bps = statistics.mean([t['actual_profit_bps'] for t in all_trades]) if all_trades else 0

    # Display overall stats
    print("OVERALL PERFORMANCE")
    print("-" * 70)
    print(f"Total Trades:          {total_trades:>10}")
    print(f"Profitable Trades:     {profitable_trades:>10}")
    print(f"Win Rate:              {win_rate:>9.2f}%")
    print(f"Total Profit (USD):    ${total_profit_usd:>9.4f}")
    print(f"Total Fees (USD):      ${total_fees:>9.4f}")
    print(f"Net Profit (USD):      ${(total_profit_usd):>9.4f}")
    print(f"Avg Profit/Trade:      ${avg_profit_usd:>9.4f}")
    print(f"Max Profit:            ${max_profit:>9.4f}")
    print(f"Min Profit:            ${min_profit:>9.4f}")
    print()

    print("PROFIT MARGINS")
    print("-" * 70)
    print(f"Avg Expected (bps):    {avg_expected_bps:>9.2f}")
    print(f"Avg Actual (bps):      {avg_actual_bps:>9.2f}")
    print(f"Slippage (bps):        {(avg_expected_bps - avg_actual_bps):>9.2f}")
    print()

    print("EXECUTION LATENCY")
    print("-" * 70)
    print(f"Avg Latency (ms):      {avg_latency:>9.2f}")
    print(f"Median Latency (ms):   {median_latency:>9.2f}")
    print(f"Min Latency (ms):      {min_latency:>9.2f}")
    print(f"Max Latency (ms):      {max_latency:>9.2f}")
    print()

    # Per-symbol statistics
    print("PER-SYMBOL BREAKDOWN")
    print("-" * 70)
    print(f"{'Symbol':<10} {'Trades':>8} {'Win%':>8} {'Total P/L':>12} {'Avg P/L':>12} {'Avg Lat':>10}")
    print("-" * 70)

    for symbol in sorted(trades_by_symbol.keys()):
        symbol_trades = trades_by_symbol[symbol]
        num_trades = len(symbol_trades)
        symbol_profit = sum(t['actual_profit_usd'] for t in symbol_trades)
        symbol_avg_profit = symbol_profit / num_trades if num_trades > 0 else 0
        symbol_profitable = sum(1 for t in symbol_trades if t['actual_profit_usd'] > 0)
        symbol_win_rate = (symbol_profitable / num_trades * 100) if num_trades > 0 else 0
        symbol_avg_latency = statistics.mean([t['latency_ms'] for t in symbol_trades])

        print(f"{symbol:<10} {num_trades:>8} {symbol_win_rate:>7.1f}% "
              f"${symbol_profit:>11.4f} ${symbol_avg_profit:>11.4f} {symbol_avg_latency:>9.1f}ms")

    print()

    # Time-based analysis
    print("TIME-BASED ANALYSIS")
    print("-" * 70)

    # Parse timestamps
    timestamps = []
    for trade in all_trades:
        try:
            # Handle both ISO formats with and without 'Z'
            ts_str = trade['timestamp']
            if 'T' in ts_str:
                # Truncate nanosecond precision to microseconds for Python compatibility
                # Format: 2025-11-16T09:01:48.772601208+00:00 -> 2025-11-16T09:01:48.772601+00:00
                if '.' in ts_str:
                    parts = ts_str.split('.')
                    if len(parts) == 2:
                        # Get fractional seconds and timezone
                        frac_and_tz = parts[1]
                        # Find where timezone starts (+ or -)
                        tz_start = max(frac_and_tz.rfind('+'), frac_and_tz.rfind('-'))
                        if tz_start > 0:
                            frac = frac_and_tz[:tz_start][:6]  # Keep only 6 digits (microseconds)
                            tz = frac_and_tz[tz_start:]
                            ts_str = f"{parts[0]}.{frac}{tz}"

                # Parse ISO format
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                timestamps.append(ts)
        except Exception as e:
            continue

    if timestamps:
        first_trade = min(timestamps)
        last_trade = max(timestamps)
        trading_duration = last_trade - first_trade

        print(f"First Trade:           {first_trade.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Last Trade:            {last_trade.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Trading Duration:      {trading_duration}")

        if trading_duration.total_seconds() > 0:
            trades_per_hour = total_trades / (trading_duration.total_seconds() / 3600)
            print(f"Trades per Hour:       {trades_per_hour:>9.2f}")
    else:
        print("No valid timestamps found")

    print()


def main():
    """Main function."""
    print_header("XEMM Trade CSV Downloader & Analyzer")

    # Step 1: Check SSH key
    if not check_ssh_key():
        sys.exit(1)

    # Step 2: Discover CSV files
    csv_files = discover_csv_files()
    if not csv_files:
        print_info("No CSV files to download. Exiting.")
        sys.exit(0)

    # Step 3: Download CSV files
    downloaded_files = download_csv_files(csv_files)
    if not downloaded_files:
        print_error("No files were downloaded successfully. Exiting.")
        sys.exit(1)

    print_success(f"Successfully downloaded {len(downloaded_files)} file(s)")

    # Step 4: Parse all CSV files
    print_info("Parsing CSV files...")
    all_trades = []
    for file_path in downloaded_files:
        trades = parse_csv_file(file_path)
        all_trades.extend(trades)
        print_info(f"Loaded {len(trades)} trades from {os.path.basename(file_path)}")

    # Step 5: Display statistics
    display_stats(all_trades)

    print_header("Download Complete")
    print_info(f"CSV files saved to: {os.path.abspath(LOCAL_DOWNLOAD_DIR)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_info("Download interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
