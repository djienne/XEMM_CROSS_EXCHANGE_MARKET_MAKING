#!/bin/bash

# XEMM Bot Runner Script
# Runs the bot a specified number of times in sequence
# Usage: ./run_bot.sh [number_of_runs]
# Example: ./run_bot.sh 10

# Default to 10 runs if no argument provided
NUM_RUNS=${1:-10}

echo "========================================"
echo "XEMM Bot Runner"
echo "Will execute $NUM_RUNS trading cycles"
echo "========================================"
echo ""

# Counter for successful runs
SUCCESS_COUNT=0
FAIL_COUNT=0

# Loop through the specified number of runs
for i in $(seq 1 $NUM_RUNS); do
    echo ""
    echo "========================================"
    echo "Starting Run #$i of $NUM_RUNS"
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    echo ""

    # Run the bot
    cargo run --release
    EXIT_CODE=$?

    # Check exit code
    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo "✓ Run #$i completed successfully"
        ((SUCCESS_COUNT++))
    else
        echo ""
        echo "✗ Run #$i failed with exit code $EXIT_CODE"
        ((FAIL_COUNT++))
    fi

    # If not the last run, add a brief pause
    if [ $i -lt $NUM_RUNS ]; then
        echo ""
        echo "Waiting 2 seconds before next run..."
        sleep 2
    fi
done

# Final summary
echo ""
echo "========================================"
echo "All runs completed!"
echo "========================================"
echo "Total runs:       $NUM_RUNS"
echo "Successful:       $SUCCESS_COUNT"
echo "Failed:           $FAIL_COUNT"
echo "Completion time:  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
