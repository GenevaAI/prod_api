import logging
from logging.config import dictConfig

# Simple version
logging.basicConfig(
    level=logging.INFO,  # or DEBUG in development
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)