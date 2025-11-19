use std::sync::Arc;
use std::time::Instant;
use tokio::sync::{mpsc, RwLock};
use colored::Colorize;

use crate::bot::{BotState, ActiveOrder};
use crate::config::Config;
use crate::connector::pacifica::{PacificaTrading, OrderSide as PacificaOrderSide};
use crate::strategy::{Opportunity, OrderSide};
use crate::util::rate_limit::RateLimitTracker;

// Macro for timestamped colored output
macro_rules! tprintln {
    ($($arg:tt)*) => {{
        println!("{} {}",
            chrono::Utc::now().format("%Y-%m-%dT%H:%M:%S%.6fZ").to_string().bright_black(),
            format!($($arg)*)
        );
    }};
}

/// Order placement request
#[derive(Debug, Clone)]
pub struct OrderPlacementRequest {
    pub opportunity: Opportunity,
    pub pac_bid: f64,
    pub pac_ask: f64,
}

/// Order placement service
///
/// Handles order placement asynchronously in a dedicated task.
/// This prevents blocking the main evaluation loop during network I/O.
pub struct OrderPlacementService {
    pub bot_state: Arc<RwLock<BotState>>,
    pub pacifica_trading: Arc<PacificaTrading>,
    pub config: Config,
    pub order_rx: mpsc::Receiver<OrderPlacementRequest>,
}

impl OrderPlacementService {
    pub async fn run(mut self) {
        let mut rate_limit = RateLimitTracker::new();

        loop {
            // Wait for order placement requests
            match self.order_rx.recv().await {
                Some(request) => {
                    // Check rate limit backoff
                    if rate_limit.should_skip() {
                        let remaining = rate_limit.remaining_backoff_secs();
                        tprintln!(
                            "{} ⚠ Skipping order placement (rate limit backoff, {:.1}s remaining)",
                            format!("[{} ORDER]", self.config.symbol).bright_yellow().bold(),
                            remaining
                        );
                        continue;
                    }

                    self.place_order(request, &mut rate_limit).await;
                }
                None => {
                    // Channel closed, exit
                    break;
                }
            }
        }
    }

    async fn place_order(&self, request: OrderPlacementRequest, rate_limit: &mut RateLimitTracker) {
        let opp = request.opportunity;
        
        tprintln!(
            "{} Placing {} on Pacifica...",
            format!("[{} ORDER]", self.config.symbol).bright_yellow().bold(),
            opp.direction.as_str().bright_yellow().bold()
        );

        let pacifica_side = match opp.direction {
            OrderSide::Buy => PacificaOrderSide::Buy,
            OrderSide::Sell => PacificaOrderSide::Sell,
        };

        match self.pacifica_trading
            .place_limit_order(
                &self.config.symbol,
                pacifica_side,
                opp.size,
                Some(opp.pacifica_price),
                0.0,
                Some(request.pac_bid),
                Some(request.pac_ask),
            )
            .await
        {
            Ok(order_data) => {
                rate_limit.record_success();

                if let Some(client_order_id) = order_data.client_order_id {
                    let order_id = order_data.order_id.unwrap_or(0);
                    tprintln!(
                        "{} {} Placed {} #{} @ {} | cloid: {}...{}",
                        format!("[{} ORDER]", self.config.symbol).bright_yellow().bold(),
                        "✓".green().bold(),
                        opp.direction.as_str().bright_yellow(),
                        order_id,
                        format!("${:.4}", opp.pacifica_price).cyan().bold(),
                        &client_order_id[..8],
                        &client_order_id[client_order_id.len()-4..]
                    );

                    let active_order = ActiveOrder {
                        client_order_id,
                        symbol: self.config.symbol.clone(),
                        side: opp.direction,
                        price: opp.pacifica_price,
                        size: opp.size,
                        initial_profit_bps: opp.initial_profit_bps,
                        placed_at: Instant::now(),
                    };

                    // Update bot state
                    let mut state = self.bot_state.write().await;
                    state.set_active_order(active_order);
                } else {
                    tprintln!(
                        "{} {} Order placed but no client_order_id returned",
                        format!("[{} ORDER]", self.config.symbol).bright_yellow().bold(),
                        "✗".red().bold()
                    );
                }
            }
            Err(e) => {
                // Check if it's a rate limit error
                if crate::util::rate_limit::is_rate_limit_error(&e) {
                    rate_limit.record_error();
                    let backoff_secs = rate_limit.get_backoff_secs();
                    tprintln!(
                        "{} {} Failed to place order: Rate limit exceeded. Backing off for {}s (attempt #{})",
                        format!("[{} ORDER]", self.config.symbol).bright_yellow().bold(),
                        "⚠".yellow().bold(),
                        backoff_secs,
                        rate_limit.consecutive_errors()
                    );
                } else {
                    tprintln!(
                        "{} {} Failed to place order: {}",
                        format!("[{} ORDER]", self.config.symbol).bright_yellow().bold(),
                        "✗".red().bold(),
                        e
                    );
                }
            }
        }
    }
}
