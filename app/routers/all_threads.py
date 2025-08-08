import threading
import logging
from app.routers.metrics_collector import fetch_and_save_metrics
from app.routers.general import fetch_and_save_aws_inventory
from app.routers.cost_schedular_code import run_cost_scheduler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def start_background_threads():
    """Start all background threads for metrics and inventory collection."""
    logger.info("Starting background threads")

    # Start AWS metrics collection thread
    # metrics_thread = threading.Thread(target=fetch_and_save_metrics, daemon=True)
    # metrics_thread.start()
    # logger.info("Started AWS metrics collection thread")

    # Start AWS inventory collection thread
    inventory_thread = threading.Thread(target=fetch_and_save_aws_inventory, daemon=True)
    inventory_thread.start()
    logger.info("Started AWS inventory collection thread")

    # Start cost scheduler thread
    cost_scheduler_thread = threading.Thread(target=run_cost_scheduler, daemon=True)
    cost_scheduler_thread.start()
    logger.info("Started cost scheduler thread")
