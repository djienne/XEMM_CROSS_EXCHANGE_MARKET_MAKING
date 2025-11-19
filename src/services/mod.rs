/// Service modules - each task runs in its own service

pub mod fill_detection;
pub mod hedge;
pub mod orderbook;
pub mod order_monitor;
pub mod position_monitor;
pub mod rest_fill_detection;
pub mod rest_poll;
pub mod order_placement;

pub use fill_detection::FillDetectionService;
pub use hedge::HedgeService;
pub use orderbook::{PacificaOrderbookService, HyperliquidOrderbookService};
pub use order_monitor::OrderMonitorService;
pub use position_monitor::PositionMonitorService;
pub use rest_fill_detection::RestFillDetectionService;
pub use rest_poll::{PacificaRestPollService, HyperliquidRestPollService};
pub use order_placement::{OrderPlacementService, OrderPlacementRequest};

use crate::strategy::OrderSide;

/// HedgeEvent represents a single hedge trigger coming from any
/// fill detection layer. It is carried through a low-latency queue
/// between the fill detection “thread(s)” and the hedge executor.
///
/// Tuple layout:
/// (side, size, avg_price, fill_detect_timestamp)
pub type HedgeEvent = (OrderSide, f64, f64, std::time::Instant);
