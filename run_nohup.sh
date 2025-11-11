#!/bin/bash
# Start the market maker bot in background with nohup
nohup cargo run --release > output.log 2>&1 &
