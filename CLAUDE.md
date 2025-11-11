# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XEMM (Cross-Exchange Market Making) is a high-performance Rust trading bot that performs single-cycle arbitrage between Pacifica (maker) and Hyperliquid (taker). The bot continuously monitors orderbook feeds from both exchanges, places limit orders on Pacifica when profitable opportunities arise, and immediately hedges fills on Hyperliquid.

## Build & Run Commands

```bash
# Check compilation
cargo check

# Build (debug)
cargo build

# Build (release/optimized)
cargo build --release

# Run main XEMM bot (src/main.rs)
cargo run
RUST_LOG=debug cargo run  # With debug logging

# Run specific examples (see complete list below in "examples/" section)
# Core examples
cargo run --example pacifica_orderbook --release
cargo run --example fill_detection_test --release
cargo run --example xemm_calculator --release

# Utility examples
cargo run --example cancel_all_test --release
cargo run --example ws_cancel_all_test --release
cargo run --example verify_wallet --release

# Symbol-specific tests
cargo run --example test_btc_orders --release

# Run tests
cargo test
cargo test --lib  # Library tests only
```

## Architecture Overview

### High-Level Bot Flow

The XEMM bot (`src/main.rs`) orchestrates 7 concurrent async tasks:

1. **Pacifica Orderbook (WebSocket)** - Real-time bid/ask feed
2. **Hyperliquid Orderbook (WebSocket)** - Real-time bid/ask feed
3. **Fill Detection (WebSocket)** - Monitors Pacifica order fills/cancellations
4. **Pacifica REST API Polling** - Fallback orderbook data (every 4s)
5. **Order Monitoring** - Profit tracking and order refresh (every 25ms)
6. **Hedge Execution** - Executes Hyperliquid hedge after fill
7. **Main Opportunity Loop** - Evaluates and places orders (every 100ms)

### Core Module Structure

```
src/
├── main.rs             # Main trading bot binary
├── lib.rs              # Library exports
├── config.rs           # Config management (loads config.json)
├── csv_logger.rs       # CSV trade history logging
├── bot/
│   ├── mod.rs
│   └── state.rs        # Bot state machine (Idle/Active/Filled/Hedged/Error)
├── strategy/
│   ├── mod.rs
│   └── opportunity.rs  # Opportunity evaluation and profit calculation
├── trade_fetcher.rs    # Post-hedge trade fetching and profit calculation utilities
└── connector/
    ├── pacifica/
    │   ├── mod.rs
    │   ├── types.rs           # WebSocket/REST message types
    │   ├── client.rs          # Orderbook WebSocket client
    │   ├── trading.rs         # REST API trading (place/cancel orders)
    │   ├── ws_trading.rs      # WebSocket trading (ultra-fast cancel_all)
    │   └── fill_detection.rs  # WebSocket fill monitoring client
    └── hyperliquid/
        ├── mod.rs
        ├── types.rs           # Data structures
        ├── client.rs          # Orderbook WebSocket client
        └── trading.rs         # REST API trading (market orders)

examples/
# Core Examples (essential testing/understanding)
├── pacifica_orderbook.rs              # View Pacifica orderbook (WebSocket live)
├── pacifica_orderbook_rest_test.rs    # Test REST API orderbook
├── fill_detection_test.rs             # Test fill detection
├── hyperliquid_market_test.rs         # Test Hyperliquid trading
├── hyperliquid_orderbook.rs           # View Hyperliquid orderbook
├── xemm_calculator.rs                 # Price calculator (no trading)
├── advanced_usage.rs                  # Advanced orderbook with statistics
├── low_latency.rs                     # Low-latency orderbook mode

# Trading Examples (educational)
├── simple_trade.rs                    # Simple trading example
├── trading_example.rs                 # Complex trading example

# Utility Examples (helper tools)
├── cancel_all_test.rs                 # Cancel all open orders (REST API)
├── ws_cancel_all_test.rs              # Test WebSocket cancel all orders
├── check_hyperliquid_symbols.rs       # Check available symbols
├── close_ena_position.rs              # Close ENA position helper
├── verify_wallet.rs                   # Verify wallet/credentials
├── debug_msgpack.rs                   # Debug MessagePack serialization
├── test_meta.rs                       # Test metadata parsing
├── test_meta_parse.rs                 # Test metadata parser
└── test_price_rounding.rs             # Test price rounding logic

# Symbol-Specific Test Examples
├── test_btc_orders.rs                 # Test BTC order placement
├── test_eth_orders.rs                 # Test ETH order placement
├── test_pengu_orders.rs               # Test PENGU order placement
├── test_pump_orders.rs                # Test PUMP order placement
└── test_xpl_orders.rs                 # Test XPL order placement

# Trade History & Position Management
├── test_pacifica_trade_history.rs     # Test Pacifica trade history API
├── test_hyperliquid_trade_history.rs  # Test Hyperliquid trade history API
├── fetch_pump_trades.rs               # Fetch PUMP trade history
├── fetch_recent_trades.rs             # Fetch recent trades utility
├── rebalancer.rs                      # Position rebalancer utility
├── rebalancer_cross_exchange.rs       # Cross-exchange rebalancer
├── check_positions_debug.rs           # Debug position checking

# Fill Detection & REST Backup
├── test_rest_fill_detection.rs        # Test REST API fill detection backup
├── test_hl_l2_snapshot.rs             # Test Hyperliquid L2 snapshot
```

### State Machine (`src/bot/state.rs`)

The bot uses a state machine to track lifecycle:

- **Idle** - Waiting for opportunity, no active order
- **Active** - Order placed on Pacifica, monitoring for fill
- **Filled** - Order filled, waiting for hedge execution
- **Hedged** - Hedge executed successfully
- **Complete** - Cycle complete, bot exits
- **Error** - Unrecoverable error occurred

State transitions are managed via `BotState` with `RwLock` for concurrent access.

### Opportunity Evaluation (`src/strategy/opportunity.rs`)

`OpportunityEvaluator` calculates optimal limit prices:

**Buy Opportunity** (Buy on Pacifica, Sell on Hyperliquid):
```
price = (HL_bid * (1 - taker_fee)) / (1 + maker_fee + profit_rate)
```

**Sell Opportunity** (Sell on Pacifica, Buy on Hyperliquid):
```
price = (HL_ask * (1 + taker_fee)) / (1 - maker_fee - profit_rate)
```

Prices are rounded to tick_size (buy rounds down, sell rounds up).

### Exchange Connectors

#### Pacifica Connector (`src/connector/pacifica/`)

**Orderbook Client** (`client.rs`):
- WebSocket: `wss://ws.pacifica.fi/ws`
- Ping interval: 15 seconds (configurable, must be ≤30s)
- Auto-reconnect: 1s first attempt, then exponential backoff capped at 30s
- Callback-based top-of-book updates

**REST Trading Client** (`trading.rs`):
- REST API for order placement/cancellation
- Ed25519 signature with canonicalized JSON (critical for auth)
- Price/size rounding to tick_size/lot_size
- Market info caching
- Functions: `place_limit_order()`, `cancel_order()`, `cancel_all_orders()`, `get_market_info()`, `get_orderbook_rest()`, `get_best_bid_ask_rest()`

**WebSocket Trading Client** (`ws_trading.rs`):
- WebSocket: `wss://ws.pacifica.fi/ws` (same endpoint as orderbook)
- Ultra-fast order cancellation with no rate limits
- Ed25519 signature per WebSocket request
- Request/response correlation via UUID
- Functions: `cancel_all_orders_ws()`
- **Use case**: High-frequency cancellations, rate limit avoidance, redundancy
- **Performance**: ~5-10ms latency vs ~50-100ms REST API
- **Alternative to REST API**: Both methods available, REST is primary

**Fill Detection Client** (`fill_detection.rs`):
- WebSocket: Subscribes to `account_order_updates` channel
- Detects partial fills, full fills, and cancellations
- Converts `OrderUpdate` to `FillEvent` for bot consumption
- Same reconnection strategy as orderbook client
- **Triggers dual cancellation** (REST + WebSocket) on fill detection

#### Hyperliquid Connector (`src/connector/hyperliquid/`)

**Orderbook Client** (`client.rs`):
- WebSocket: `wss://api.hyperliquid.xyz/ws`
- Request-response pattern for L2 book snapshots
- Request interval: 100ms (configurable)
- Subscription ID tracking for correlation

**Trading Client** (`trading.rs`):
- REST API for market orders
- EIP-712 signature for Ethereum-based auth
- Functions: `market_order()`, `get_user_state()`, `cancel_all_orders()`
- Slippage protection via `slippage` parameter

### Configuration System (`config.rs`)

Loads `config.json` with validation:

```json
{
  "symbol": "SOL",
  "reconnect_attempts": 5,
  "ping_interval_secs": 15,
  "pacifica_maker_fee_bps": 1.5,
  "hyperliquid_taker_fee_bps": 4.0,
  "profit_rate_bps": 15.0,
  "order_notional_usd": 20.0,
  "profit_cancel_threshold_bps": 3.0,
  "order_refresh_interval_secs": 60,
  "hyperliquid_slippage": 0.05,
  "pacifica_rest_poll_interval_secs": 2
}
```

**Key parameters:**
- `symbol`: Trading symbol (must exist on both exchanges)
- `ping_interval_secs`: Must be 1-30 seconds
- `profit_cancel_threshold_bps`: Cancel if profit deviates ±3 bps
- `order_refresh_interval_secs`: Auto-cancel stale orders (default 60s)
- `pacifica_rest_poll_interval_secs`: REST API fallback polling (default 2s)
- `profit_rate_bps`: Target profit in basis points (default 15 bps)

### Monitoring & Order Management

**Order Monitoring Task** (Task 5 in `src/main.rs`):
- Runs every 25ms (40 Hz)
- **Age check**: Cancels orders older than `order_refresh_interval_secs`
- **Profit check**: Cancels if profit deviates by more than `profit_cancel_threshold_bps` in either direction (increase or decrease)
- Logs current profit every 2 seconds

**Profit Deviation Logic**:
- If profit drops >3 bps: Market moved against us → cancel and replace
- If profit increases >3 bps: Market moved favorably → cancel and place at better price

### Trading Workflow

1. **Startup**: Cancel all existing Pacifica orders
2. **Wait**: Gather initial orderbook data (3s)
3. **Evaluate**: Check both BUY and SELL opportunities every 100ms
4. **Place**: If profitable (>target profit), place limit order on Pacifica
5. **Monitor**: Track profit every 25ms, cancel if deviation >3 bps or age >30s
6. **Fill**: Fill detection WebSocket notifies when order fills
   - **Dual Cancellation**: Immediately cancel all orders via REST + WebSocket (defense in depth)
7. **Hedge**: Execute market order on Hyperliquid (opposite direction)
8. **Wait**: 20-second delay for trades to propagate to exchange APIs
9. **Fetch**: Retrieve actual fill data from both exchanges with retry logic
10. **Calculate**: Compute actual profit using real fills and fees
11. **Complete**: Display comprehensive profit summary and exit

### Dual Cancellation Safety (Race Condition Mitigation)

**Problem**: When a fill is detected, there's a critical window where stray orders could remain active, leading to:
- Multiple fills without hedges
- Unintended position accumulation
- Loss of capital due to unhedged exposure

**Solution**: The bot implements **defense in depth** with dual cancellation:

1. **REST API Cancellation** (~50-100ms latency)
   - Reliable, well-tested method
   - Primary cancellation mechanism
   - May hit rate limits under high frequency

2. **WebSocket Cancellation** (~5-10ms latency)
   - Ultra-fast, no rate limits
   - Secondary safety net
   - Catches any orders missed by REST API

**Implementation** (`src/main.rs` - Fill Detection Task):
```rust
// First: REST API cancel
let rest_result = pacifica_trading.cancel_all_orders(...).await;

// Second: WebSocket cancel (immediately after)
let ws_result = pacifica_ws_trading.cancel_all_orders_ws(...).await;
```

**Benefits**:
- **Redundancy**: One method fails → other succeeds
- **Speed**: WebSocket provides 5-10x faster cancellation
- **No rate limits**: WebSocket bypasses REST API rate limits
- **Fault tolerance**: Network issues with one method don't affect the other
- **Race condition mitigation**: Dual coverage reduces timing windows

**Testing**: Both methods tested in production (see `examples/ws_cancel_all_test.rs`)

### REST API Fill Detection Backup (`examples/test_rest_fill_detection.rs`)

**Fallback System**: In addition to WebSocket fill detection, the bot has a REST API polling backup that detects fills if the WebSocket fails:

- **Polling interval**: 500ms (configurable)
- **Detection method**: Compares open orders against last known state
- **Use case**: WebSocket connection failure, missed messages
- **Triggers**: Same dual cancellation + hedge execution flow
- **No duplicate hedges**: State machine prevents double-execution

This provides an additional layer of redundancy for critical fill detection.

### CSV Trade Logging (`src/csv_logger.rs`)

The bot logs completed trades to a CSV file for historical tracking and analysis:

**Trade Record Fields**:
- Timestamp (ISO 8601 format)
- Symbol, sides, prices, sizes, notionals
- Fees (Pacifica, Hyperliquid, total)
- Expected vs actual profit (bps and USD)
- Gross PnL before fees

**Usage**:
```rust
use xemm_rust::csv_logger::{TradeRecord, log_trade};

let record = TradeRecord::new(
    Utc::now(),
    symbol,
    pacifica_side,
    pac_price, pac_size, pac_notional, pac_fee,
    hl_price, hl_size, hl_notional, hl_fee,
    expected_profit_bps,
    actual_profit_bps,
    actual_profit_usd,
);

log_trade("trades_history.csv", &record)?;
```

The CSV file is automatically created with headers if it doesn't exist, and new trades are appended.

### Trade Fetching & Profit Calculation (`src/trade_fetcher.rs`)

After hedge execution, the bot waits 20 seconds for trades to propagate to exchange APIs, then fetches actual fill data:

**Pacifica Trade Fetching**:
- Fetches last 20 trades via `get_trade_history()` API
- Matches trades by `client_order_id`
- Handles single fills or multiple partial fills (calculates weighted average)
- Extracts actual fees paid from trade records
- Retry logic: 3 attempts with delays (5s, 10s, 15s)

**Hyperliquid Trade Fetching**:
- Fetches user fills via `get_user_fills()` with time aggregation
- Filters recent fills by symbol (within 10-second window)
- Calculates weighted average for multiple fills
- Sums actual fees paid across all fills
- Retry logic: 3 attempts with delays (5s, 10s, 15s)

**Profit Calculation** (`calculate_hedge_profit()`):
```rust
gross_pnl = if is_pacifica_buy {
    hl_notional - pac_notional
} else {
    pac_notional - hl_notional
}
net_profit = gross_pnl - pac_fee - hl_fee
profit_bps = (net_profit / pac_notional) * 10000
```

**Key Features**:
- Uses actual notional values from exchanges (not recalculated)
- Handles multi-fill trades correctly
- Falls back to theoretical fees if actual fees unavailable
- Shared calculation function (same as test utilities)

### Ed25519 Signature Process (Pacifica)

Critical for authentication - incorrect canonicalization causes signature failures:

1. Build header: `{type: "agent", timestamp: <ms>, expiry_window: 5000}`
2. Build payload with order parameters
3. Combine: `{...header, data: payload}`
4. **Canonicalize JSON**:
   - Recursively sort all object keys alphabetically
   - Compact format (no spaces)
   - Proper string escaping
5. Sign with Ed25519 using **first 32 bytes** of 64-byte Solana private key
6. Encode signature as Base58

Implementation: `canonicalize_json()` in `src/connector/pacifica/trading.rs`

### WebSocket Reconnection Strategy

All WebSocket clients use the same reconnection logic:
- **First attempt**: 1 second delay
- **Subsequent attempts**: Exponential backoff `2^(n-1)` seconds
- **Maximum backoff**: 30 seconds
- **Ping/pong**: Every 15 seconds (prevents 30s server timeout)

### REST API Fallback (Pacifica)

The bot uses dual-source orderbook data:
- **Primary**: WebSocket subscription (real-time, <10ms latency)
- **Fallback**: REST API polling every 4s (configurable)

Both update the same shared `Arc<Mutex<(f64, f64)>>` state, ensuring seamless failover.

## Performance Tuning

- **Monitoring interval**: 25ms (40 Hz) for profit checks
- **Opportunity evaluation**: 100ms (10 Hz) for new order placement
- **Pacifica REST polling**: 4s (0.25 Hz) as fallback
- **Hyperliquid L2 requests**: 100ms (10 Hz)
- **Logging precision**: 6 decimal places for low-priced coins (e.g., ENA at $0.39)

## Terminal Output & User Interface

The bot uses the `colored` crate to provide rich, colorized terminal output for easy monitoring and debugging.

### Color Scheme Implementation

**Section Labels** (color-coded by task type):
- `[CONFIG]` - Blue bold - Configuration values
- `[INIT]` - Cyan bold - Initialization steps
- `[PACIFICA_OB]` / `[HYPERLIQUID_OB]` - Magenta bold - Orderbook feeds
- `[FILL_DETECTION]` - Magenta bold - Fill detection events
- `[MONITOR]` - Yellow bold - Profit monitoring warnings
- `[PROFIT]` - Bright blue bold - Profit update logs
- `[OPPORTUNITY]` - Bright green bold - Arbitrage opportunities detected
- `[ORDER]` - Bright yellow bold - Order placement
- `[HEDGE]` - Bright magenta bold - Hedge execution
- `[SHUTDOWN]` - Yellow bold - Cleanup operations

**Status Indicators**:
- ✓ (Green bold) - Success checkmarks
- ✗ (Red bold) - Error/failure marks
- ⚠ (Yellow bold) - Warning symbols

**Trading Data**:
- Prices: Cyan (bold for important prices)
- Symbols: Bright white bold
- Amounts/Sizes: Bright white
- BUY orders/actions: Green (bold)
- SELL orders/actions: Red (bold)
- Profit increasing: Green
- Profit decreasing/dropped: Red
- Fees: Yellow

**Special Formatting**:
- Trade completion summary: Green bold borders with emoji headers (📊, 💰, 📈)
- Headers/separators: Bright cyan bold (═══)

### Implementation Details

Colors are applied using the `colored` crate's trait methods:
```rust
use colored::Colorize;

info!("{} {}", "[INIT]".cyan().bold(), "Credentials loaded".green());
info!("{} {} Placed {} @ {}",
    "[ORDER]".bright_yellow().bold(),
    "✓".green().bold(),
    "BUY".green(),
    format!("${:.4}", price).cyan().bold()
);
```

The colored output makes it easy to:
- Quickly spot errors and warnings
- Track profit changes at a glance
- Monitor order flow and state transitions
- Distinguish between different exchange feeds

## Important Notes

- **Mainnet only**: Production system, uses real funds
- **Single-cycle**: Bot exits after one successful hedge
- **No position accumulation**: Always hedges immediately after fill
- **Graceful shutdown**: Ctrl+C cancels remaining orders before exit
- **Credentials**: Load from `.env` file (never commit)
  - Pacifica: `PACIFICA_API_KEY`, `PACIFICA_SECRET_KEY`, `PACIFICA_ACCOUNT`
  - Hyperliquid: `HL_WALLET`, `HL_PRIVATE_KEY`

## Common Development Patterns

### Adding a New Exchange Connector

1. Create module in `src/connector/<exchange>/`
2. Define types in `types.rs` (WebSocket messages, API responses)
3. Implement orderbook client in `client.rs` (WebSocket with callbacks)
4. Implement trading client in `trading.rs` (REST API with auth)
5. Add credentials struct with `from_env()` method
6. Export in `src/connector/mod.rs`

### Modifying Bot Logic

Main bot logic is in `src/main.rs`:
- Task 1-4: Data ingestion (orderbook feeds)
- Task 5: Order monitoring and cancellation logic
- Task 6: Hedge execution and profit calculation (uses `trade_fetcher` module)
- Task 7: Main opportunity evaluation loop

State changes should go through `BotState` methods in `src/bot/state.rs`.

**Important**: When modifying hedge execution (Task 6), ensure `state.mark_complete()` is called **after** the profit summary is displayed, not before. Calling it too early causes a race condition where the main loop exits before profit calculation completes.

### Position Rebalancer (`examples/rebalancer.rs`)

Utility for checking and rebalancing position imbalances on Hyperliquid:

```bash
# Check all positions
cargo run --example rebalancer --release

# Check specific symbol
cargo run --example rebalancer --release -- --symbol SOL

# Set custom threshold
cargo run --example rebalancer --release -- --threshold 50.0

# Dry run (check without executing)
cargo run --example rebalancer --release -- --dry-run
```

**Features**:
- Checks all open positions on Hyperliquid
- Automatically rebalances if notional value exceeds threshold
- Uses market orders for fast execution
- Colorized output with position details

### Testing Trading Operations

Always test with small notional values first:
1. Set `order_notional_usd: 5.0` in config.json
2. Run with `RUST_LOG=debug` to see all messages
3. Monitor fills via fill detection WebSocket
4. Check profit calculations in logs

### Price Precision

Low-priced coins (e.g., ENA ~$0.39) require higher precision:
- Display: 6 decimal places (e.g., `${:.6}`)
- Calculations: Use f64 throughout
- Rounding: Always round to tick_size before API calls

## Deployment

See `DEPLOYMENT.md` for Docker deployment to VPS.

Key files:
- `Dockerfile` - Multi-stage build with Rust
- `docker-compose.yml` - Service definition with restart policy
- `.env` - API credentials (never commit)
- `config.json` - Bot parameters

## Critical Bug Fixes

### Race Condition Fix - Multiple Unhedged Fills (Fixed 2025-11-04)

**Problem**: Bot experienced multiple consecutive fills without hedging due to a race condition in the cancellation handler.

**Root Cause**: The cancellation handler unconditionally reset the bot state to `Idle` when receiving cancellation confirmations from the dual-cancel safety mechanism, even if the bot was in the middle of hedge execution. This allowed the main loop to place new orders while a hedge was still executing.

**Solution**: The cancellation handler now checks the current state before resetting to `Idle`:
- **OrderPlaced state**: Normal cancellation → reset to Idle ✓
- **Filled/Hedging/Complete states**: Post-fill cancellation → ignore, preserve state ✓

**Location**: `src/main.rs:372-397`

**Testing**: Enable `RUST_LOG=debug` to see state transitions. Look for log messages like:
```
[BOT] Cancellation confirmed for order in Filled state (ignoring, hedge in progress)
```

This indicates the fix is working correctly.

**Documentation**: See `RACE_CONDITION_FIX.md` for detailed analysis and timeline reconstruction.

## Troubleshooting

**Signature verification failed:**
- Check Ed25519 key is correct (first 32 bytes of Solana key)
- Verify JSON canonicalization matches Python SDK
- Ensure timestamp is current (within 5s)

**Order rejected:**
- Verify price is rounded to tick_size
- Verify size is rounded to lot_size
- Check market info is up to date

**WebSocket disconnects:**
- Ensure ping interval ≤30 seconds (default: 15s)
- Check network stability
- Review logs for specific errors

**No opportunities detected:**
- Verify both orderbook feeds are connected
- Check fee configuration (maker + taker fees)
- Ensure profit_rate_bps is realistic (default: 10 bps)
- Review spread between exchanges

**Fill not detected:**
- Check fill detection WebSocket is connected
- Verify account address matches credentials
- Enable debug logging: `RUST_LOG=debug`

**Profit calculation not displayed after hedge:**
- Ensure `state.mark_complete()` is called **after** profit display, not before
- This was a known race condition: marking complete too early caused main loop to exit immediately
- Fixed in commit that moved `mark_complete()` to after the profit summary block

**Multiple unhedged fills / position imbalances:**
- This was caused by a critical race condition in the cancellation handler (FIXED 2025-11-04)
- The handler now preserves state during hedge execution
- Enable `RUST_LOG=debug` to monitor state transitions
- Use `examples/rebalancer.rs` to check and fix position imbalances
- See `RACE_CONDITION_FIX.md` for detailed analysis

## Code Organization & Duplication

**IMPORTANT**: The codebase should have only **one** main binary entry point: `src/main.rs`.

Previously, there was code duplication between `src/main.rs` and `src/bin/xemm_bot.rs`, which led to:
- Version inconsistencies (one with 20s wait, one without)
- Difficult maintenance (fixes needed in two places)
- Confusion about which version was running

**Rule**: Never duplicate the main bot logic. Keep all bot orchestration in `src/main.rs`. Use modules (`src/trade_fetcher.rs`, `src/strategy/`, `src/connector/`) for reusable components that can be tested independently via examples.
