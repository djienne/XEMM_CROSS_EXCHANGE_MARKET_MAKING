#!/usr/bin/env python3
"""
Script to collect all Rust source code files into a single text file
with separation headers for each file.
"""

import os
from pathlib import Path
from datetime import datetime


def should_exclude_path(path_str: str) -> bool:
    """Check if a path should be excluded from collection."""
    exclude_dirs = [
        'target',
        '.git',
        'node_modules',
        '__pycache__',
        '.venv',
        'venv',
    ]

    for exclude in exclude_dirs:
        if f'{os.sep}{exclude}{os.sep}' in path_str or path_str.endswith(f'{os.sep}{exclude}'):
            return True
    return False


def collect_rust_files(root_dir: str, output_file: str):
    """
    Collect all Rust (.rs) files and write them to a single output file.

    Args:
        root_dir: Root directory to search for Rust files
        output_file: Output text file path
    """
    root_path = Path(root_dir)
    rust_files = []

    # Find all .rs files, excluding target and other build directories
    print("Searching for Rust files...")
    for rs_file in root_path.rglob('*.rs'):
        if not should_exclude_path(str(rs_file)):
            rust_files.append(rs_file)

    # Sort files for consistent output
    rust_files.sort()

    print(f"Found {len(rust_files)} Rust files")

    # Write to output file
    with open(output_file, 'w', encoding='utf-8') as out:
        # Write header
        out.write("=" * 80 + "\n")
        out.write("RUST SOURCE CODE COLLECTION\n")
        out.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write(f"Total files: {len(rust_files)}\n")
        out.write("=" * 80 + "\n\n")

        # Write each file
        for idx, file_path in enumerate(rust_files, 1):
            relative_path = file_path.relative_to(root_path)

            print(f"Processing [{idx}/{len(rust_files)}]: {relative_path}")

            # Write separator and file header
            out.write("\n" + "=" * 80 + "\n")
            out.write(f"FILE: {relative_path}\n")
            out.write(f"PATH: {file_path}\n")
            out.write("=" * 80 + "\n\n")

            # Write file content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    out.write(content)
                    # Ensure there's a newline at the end
                    if content and not content.endswith('\n'):
                        out.write('\n')
            except Exception as e:
                out.write(f"ERROR: Could not read file: {e}\n")

            out.write("\n")

    print(f"\nSuccessfully created {output_file}")
    print(f"Collected {len(rust_files)} Rust files")


if __name__ == "__main__":
    # Set paths
    root_directory = os.path.dirname(os.path.abspath(__file__))
    output_filename = "rust_code_collection.txt"

    print(f"Root directory: {root_directory}")
    print(f"Output file: {output_filename}\n")

    collect_rust_files(root_directory, output_filename)
