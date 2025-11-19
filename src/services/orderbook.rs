use std::sync::{Arc, Mutex};
use anyhow::{Context, Result};
use colored::Colorize;

use crate::connector::pacifica::{OrderbookClient as PacificaOrderbookClient, OrderbookConfig as PacificaOrderbookConfig};
use crate::connector::hyperliquid::{OrderbookClient as HyperliquidOrderbookClient, OrderbookConfig as HyperliquidOrderbookConfig};

// Macro for timestamped colored output
macro_rules! tprintln {
    ($($arg:tt)*) => {{
        println!("{} {}",
            chrono::Utc::now().format("%Y-%m-%dT%H:%M:%S%.6fZ").to_string().bright_black(),
            format!($($arg)*)
        );
    }};
}

/// Pacifica orderbook service
///
/// Subscribes to Pacifica orderbook WebSocket and updates shared price state.
/// Provides real-time bid/ask prices for opportunity evaluation.
pub struct PacificaOrderbookService {
    pub prices: Arc<Mutex<(f64, f64)>>,
    pub symbol: String,
    pub agg_level: u32,
    pub reconnect_attempts: u32,
    pub ping_interval_secs: u64,
    pub price_update_tx: tokio::sync::broadcast::Sender<()>,
}

impl PacificaOrderbookService {
    pub async fn run(self) -> Result<()> {
        let pac_prices_clone = self.prices.clone();
        let price_update_tx_clone = self.price_update_tx.clone();
        let pacifica_ob_config = PacificaOrderbookConfig {
            symbol: self.symbol.clone(),
            agg_level: self.agg_level,
            reconnect_attempts: self.reconnect_attempts,
            ping_interval_secs: self.ping_interval_secs,
        };

        let mut pacifica_ob_client = PacificaOrderbookClient::new(pacifica_ob_config)
            .context("Failed to create Pacifica orderbook client")?;

        tprintln!("{} Starting orderbook client", "[PACIFICA_OB]".magenta().bold());
        pacifica_ob_client
            .start(move |book_data| {
                // Extract top of book using zero-copy accessor (optimized for latency)
                // Note: book_data contains full depth which can be used for VWAP later
                if let Some((bid_str, ask_str)) = book_data.get_best_bid_ask() {
                    // Parse strings directly without intermediate allocations
                    let bid_price: f64 = bid_str.parse().unwrap_or(0.0);
                    let ask_price: f64 = ask_str.parse().unwrap_or(0.0);
                    *pac_prices_clone.lock().unwrap() = (bid_price, ask_price);
                    
                    // Notify subscribers of price update (triggers opportunity evaluation + order monitoring)
                    let _ = price_update_tx_clone.send(());
                }
            })
            .await
            .ok();

        Ok(())
    }
}

/// Hyperliquid orderbook service
///
/// Subscribes to Hyperliquid orderbook WebSocket and updates shared price state.
/// Provides real-time bid/ask prices for hedge execution.
pub struct HyperliquidOrderbookService {
    pub prices: Arc<Mutex<(f64, f64)>>,
    pub symbol: String,
    pub reconnect_attempts: u32,
    pub ping_interval_secs: u64,
    pub request_interval_ms: u64,
    pub price_update_tx: tokio::sync::broadcast::Sender<()>,
}

impl HyperliquidOrderbookService {
    pub async fn run(self) -> Result<()> {
        let hl_prices_clone = self.prices.clone();
        let price_update_tx_clone = self.price_update_tx.clone();
        let hyperliquid_ob_config = HyperliquidOrderbookConfig {
            coin: self.symbol.clone(),
            reconnect_attempts: self.reconnect_attempts,
            ping_interval_secs: self.ping_interval_secs,
            request_interval_ms: self.request_interval_ms,
        };

        let mut hyperliquid_ob_client = HyperliquidOrderbookClient::new(hyperliquid_ob_config)
            .context("Failed to create Hyperliquid orderbook client")?;

        tprintln!("{} Starting orderbook client", "[HYPERLIQUID_OB]".magenta().bold());
        hyperliquid_ob_client
            .start(move |book_data| {
                // Extract top of book using zero-copy accessor (optimized for latency)
                if let Some((bid_str, ask_str)) = book_data.get_best_bid_ask() {
                    // Parse strings directly without intermediate allocations
                    let bid_price: f64 = bid_str.parse().unwrap_or(0.0);
                    let ask_price: f64 = ask_str.parse().unwrap_or(0.0);
                    *hl_prices_clone.lock().unwrap() = (bid_price, ask_price);
                    
                    // Notify subscribers of price update (triggers opportunity evaluation + order monitoring)
                    let _ = price_update_tx_clone.send(());
                }
            })
            .await
            .ok();

        Ok(())
    }
}
