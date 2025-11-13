use anyhow::{Context, Result};
use std::collections::HashSet;
use std::sync::Arc;
use std::sync::Mutex;
use std::time::Instant;
use tokio::sync::{mpsc, RwLock};

use crate::bot::BotState;
use crate::config::Config;
use crate::connector::hyperliquid::{HyperliquidCredentials, HyperliquidTrading};
use crate::connector::pacifica::{PacificaCredentials, PacificaTrading, PacificaWsTrading};
use crate::strategy::{OpportunityEvaluator, OrderSide};

/// Position snapshot for tracking position deltas
#[derive(Debug, Clone)]
pub struct PositionSnapshot {
    pub amount: f64,
    pub side: String, // "bid" or "ask"
    pub last_check: Instant,
}

/// XemmBot - Main application structure that encapsulates all bot components
pub struct XemmBot {
    pub config: Config,
    pub bot_state: Arc<RwLock<BotState>>,

    // Trading clients (each task gets its own instance to avoid lock contention)
    pub pacifica_trading_main: Arc<PacificaTrading>,
    pub pacifica_trading_fill: Arc<PacificaTrading>,
    pub pacifica_trading_rest_fill: Arc<PacificaTrading>,
    pub pacifica_trading_monitor: Arc<PacificaTrading>,
    pub pacifica_trading_hedge: Arc<PacificaTrading>,
    pub pacifica_trading_rest_poll: Arc<PacificaTrading>,
    pub pacifica_ws_trading: Arc<PacificaWsTrading>,
    pub hyperliquid_trading: Arc<HyperliquidTrading>,

    // Shared state (prices)
    pub pacifica_prices: Arc<Mutex<(f64, f64)>>, // (bid, ask)
    pub hyperliquid_prices: Arc<Mutex<(f64, f64)>>, // (bid, ask)

    // Opportunity evaluator
    pub evaluator: OpportunityEvaluator,

    // Fill tracking state
    pub processed_fills: Arc<tokio::sync::Mutex<HashSet<String>>>,
    pub last_position_snapshot: Arc<tokio::sync::Mutex<Option<PositionSnapshot>>>,

    // Channels
    pub hedge_tx: mpsc::Sender<(OrderSide, f64, f64)>,
    pub hedge_rx: Option<mpsc::Receiver<(OrderSide, f64, f64)>>,
    pub shutdown_tx: mpsc::Sender<()>,
    pub shutdown_rx: Option<mpsc::Receiver<()>>,

    // Credentials (needed for spawning services)
    pub pacifica_credentials: PacificaCredentials,
}

impl XemmBot {
    /// Create and initialize a new XemmBot instance
    ///
    /// This performs all the wiring:
    /// - Loads config and validates it
    /// - Loads credentials from environment
    /// - Creates all trading clients
    /// - Pre-fetches Hyperliquid metadata
    /// - Cancels existing orders
    /// - Fetches Pacifica tick size
    /// - Creates OpportunityEvaluator
    /// - Initializes shared state and channels
    pub async fn new() -> Result<Self> {
        use colored::Colorize;

        println!(
            "{} {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "═══════════════════════════════════════════════════"
                .bright_cyan()
                .bold()
        );
        println!(
            "{} {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "  XEMM Bot - Cross-Exchange Market Making"
                .bright_cyan()
                .bold()
        );
        println!(
            "{} {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "═══════════════════════════════════════════════════"
                .bright_cyan()
                .bold()
        );
        println!();

        // Load configuration
        let config = Config::load_default().context("Failed to load config.json")?;
        config.validate().context("Invalid configuration")?;

        println!(
            "{} {} Symbol: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            config.symbol.bright_white().bold()
        );
        println!(
            "{} {} Order Notional: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            format!("${:.2}", config.order_notional_usd).bright_white()
        );
        println!(
            "{} {} Pacifica Maker Fee: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            format!("{} bps", config.pacifica_maker_fee_bps).bright_white()
        );
        println!(
            "{} {} Hyperliquid Taker Fee: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            format!("{} bps", config.hyperliquid_taker_fee_bps).bright_white()
        );
        println!(
            "{} {} Target Profit: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            format!("{} bps", config.profit_rate_bps).green().bold()
        );
        println!(
            "{} {} Profit Cancel Threshold: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            format!("{} bps", config.profit_cancel_threshold_bps).yellow()
        );
        println!(
            "{} {} Order Refresh Interval: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            format!("{} secs", config.order_refresh_interval_secs).bright_white()
        );
        println!(
            "{} {} Pacifica REST Poll Interval: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            format!("{} secs", config.pacifica_rest_poll_interval_secs).bright_white()
        );
        println!(
            "{} {} Hyperliquid Market Order maximum allowed Slippage: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[CONFIG]".blue().bold(),
            format!("{}%", config.hyperliquid_slippage * 100.0).bright_white()
        );
        println!();

        // Load credentials
        dotenv::dotenv().ok();
        let pacifica_credentials =
            PacificaCredentials::from_env().context("Failed to load Pacifica credentials from environment")?;
        let hyperliquid_credentials =
            HyperliquidCredentials::from_env().context("Failed to load Hyperliquid credentials from environment")?;

        println!(
            "{} {} {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[INIT]".cyan().bold(),
            "Credentials loaded successfully".green()
        );

        // Initialize trading clients
        let pacifica_trading_main = Arc::new(
            PacificaTrading::new(pacifica_credentials.clone())
                .context("Failed to create main Pacifica trading client")?,
        );
        let pacifica_trading_fill = Arc::new(
            PacificaTrading::new(pacifica_credentials.clone())
                .context("Failed to create fill detection Pacifica trading client")?,
        );
        let pacifica_trading_rest_fill = Arc::new(
            PacificaTrading::new(pacifica_credentials.clone())
                .context("Failed to create REST fill detection Pacifica trading client")?,
        );
        let pacifica_trading_monitor = Arc::new(
            PacificaTrading::new(pacifica_credentials.clone())
                .context("Failed to create monitor Pacifica trading client")?,
        );
        let pacifica_trading_hedge = Arc::new(
            PacificaTrading::new(pacifica_credentials.clone())
                .context("Failed to create hedge Pacifica trading client")?,
        );
        let pacifica_trading_rest_poll = Arc::new(
            PacificaTrading::new(pacifica_credentials.clone())
                .context("Failed to create REST polling Pacifica trading client")?,
        );

        // Initialize WebSocket trading client for ultra-fast cancellations
        let pacifica_ws_trading = Arc::new(PacificaWsTrading::new(pacifica_credentials.clone(), false)); // false = mainnet

        let hyperliquid_trading = Arc::new(
            HyperliquidTrading::new(hyperliquid_credentials, false)
                .context("Failed to create Hyperliquid trading client")?,
        );

        println!(
            "{} {} {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[INIT]".cyan().bold(),
            "Trading clients initialized (6 REST instances + WebSocket)".green()
        );

        // Pre-fetch Hyperliquid metadata (szDecimals, etc.) to reduce hedge latency
        println!(
            "{} {} Pre-fetching Hyperliquid metadata for {}...",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[INIT]".cyan().bold(),
            config.symbol.bright_white()
        );
        hyperliquid_trading
            .get_meta()
            .await
            .context("Failed to pre-fetch Hyperliquid metadata")?;
        println!(
            "{} {} {} Hyperliquid metadata cached",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[INIT]".cyan().bold(),
            "✓".green().bold()
        );

        // Cancel any existing orders on Pacifica at startup
        println!(
            "{} {} Cancelling any existing orders on Pacifica...",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[INIT]".cyan().bold()
        );
        match pacifica_trading_main
            .cancel_all_orders(false, Some(&config.symbol), false)
            .await
        {
            Ok(count) => println!(
                "{} {} {} Cancelled {} existing order(s)",
                chrono::Utc::now()
                    .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                    .to_string()
                    .bright_black(),
                "[INIT]".cyan().bold(),
                "✓".green().bold(),
                count
            ),
            Err(e) => println!(
                "{} {} {} Failed to cancel existing orders: {}",
                chrono::Utc::now()
                    .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                    .to_string()
                    .bright_black(),
                "[INIT]".cyan().bold(),
                "⚠".yellow().bold(),
                e
            ),
        }

        // Get market info to determine tick size
        let pacifica_tick_size: f64 = {
            let market_info = pacifica_trading_main
                .get_market_info()
                .await
                .context("Failed to fetch Pacifica market info")?;
            let symbol_info = market_info
                .get(&config.symbol)
                .with_context(|| format!("Symbol {} not found in market info", config.symbol))?;
            symbol_info.tick_size.parse().context("Failed to parse tick size")?
        };

        println!(
            "{} {} Pacifica tick size for {}: {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[INIT]".cyan().bold(),
            config.symbol.bright_white(),
            format!("{}", pacifica_tick_size).bright_white()
        );

        // Create opportunity evaluator
        let evaluator = OpportunityEvaluator::new(
            config.pacifica_maker_fee_bps,
            config.hyperliquid_taker_fee_bps,
            config.profit_rate_bps,
            pacifica_tick_size,
        );

        println!(
            "{} {} {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[INIT]".cyan().bold(),
            "Opportunity evaluator created".green()
        );

        // Shared state for orderbook prices
        let pacifica_prices = Arc::new(Mutex::new((0.0, 0.0))); // (bid, ask)
        let hyperliquid_prices = Arc::new(Mutex::new((0.0, 0.0))); // (bid, ask)

        // Shared bot state
        let bot_state = Arc::new(RwLock::new(BotState::new()));

        // Channels for communication
        let (hedge_tx, hedge_rx) = mpsc::channel::<(OrderSide, f64, f64)>(1); // (side, size, avg_price)
        let (shutdown_tx, shutdown_rx) = mpsc::channel::<()>(1);

        // Fill tracking state
        let processed_fills = Arc::new(tokio::sync::Mutex::new(HashSet::<String>::new()));
        let last_position_snapshot = Arc::new(tokio::sync::Mutex::new(Option::<PositionSnapshot>::None));

        println!(
            "{} {} {}",
            chrono::Utc::now()
                .format("%Y-%m-%dT%H:%M:%S%.6fZ")
                .to_string()
                .bright_black(),
            "[INIT]".cyan().bold(),
            "State and channels initialized".green()
        );
        println!();

        Ok(XemmBot {
            config,
            bot_state,
            pacifica_trading_main,
            pacifica_trading_fill,
            pacifica_trading_rest_fill,
            pacifica_trading_monitor,
            pacifica_trading_hedge,
            pacifica_trading_rest_poll,
            pacifica_ws_trading,
            hyperliquid_trading,
            pacifica_prices,
            hyperliquid_prices,
            evaluator,
            processed_fills,
            last_position_snapshot,
            hedge_tx,
            hedge_rx: Some(hedge_rx),
            shutdown_tx,
            shutdown_rx: Some(shutdown_rx),
            pacifica_credentials,
        })
    }

    /// Run the bot - spawn all services and execute main loop
    pub async fn run(self) -> Result<()> {
        // TODO: This will be implemented in later phases
        // For now, just return Ok to allow compilation
        Ok(())
    }
}
