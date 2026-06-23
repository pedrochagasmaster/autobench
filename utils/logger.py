"""
Logger - Logging configuration and utilities.

Sets up structured logging for the benchmarking tool.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logging(
    log_level: str = 'INFO',
    log_file: Optional[str] = None,
    console_output: bool = True
) -> logging.Logger:
    """
    Configure logging for the application.
    
    Parameters:
    -----------
    log_level : str
        Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
    log_file : str, optional
        Path to log file
    console_output : bool
        Whether to output to console
        
    Returns:
    --------
    logging.Logger
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        # Ensure directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    logger.info(f"Logging initialized at {log_level} level")
    if log_file:
        logger.info(f"Log file: {log_file}")
    
    return logger


def create_analysis_logger(
    entity_name: str,
    analysis_type: str,
    log_dir: str = '.'
) -> logging.Logger:
    """
    Create a logger specific to an analysis run.
    
    Parameters:
    -----------
    entity_name : str
        Name of entity being analyzed
    analysis_type : str
        Type of analysis
    log_dir : str
        Directory for log files
        
    Returns:
    --------
    logging.Logger
        Configured analysis logger
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = Path(log_dir) / f"analysis_{entity_name}_{analysis_type}_{timestamp}.log"
    
    logger = setup_logging(
        log_level='INFO',
        log_file=str(log_file),
        console_output=True
    )
    
    logger.info("=" * 80)
    logger.info(f"BENCHMARK ANALYSIS - {analysis_type.upper()}")
    logger.info(f"Entity: {entity_name}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 80)
    
    return logger


class AnalysisLogger:
    """
    Context manager for analysis logging.
    
    Provides structured logging with automatic start/end markers.
    """
    
    def __init__(
        self,
        operation: str,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize analysis logger.
        
        Parameters:
        -----------
        operation : str
            Name of the operation being logged
        logger : logging.Logger, optional
            Logger instance to use
        """
        self.operation = operation
        self.logger = logger or logging.getLogger(__name__)
        self.start_time = None
    
    def __enter__(self):
        """Start logging context."""
        self.start_time = datetime.now()
        self.logger.info(f"Starting: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End logging context."""
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.info(f"Completed: {self.operation} (duration: {duration:.2f}s)")
        else:
            self.logger.error(
                f"Failed: {self.operation} (duration: {duration:.2f}s) - "
                f"{exc_type.__name__}: {exc_val}"
            )
        
        return False  # Don't suppress exceptions
    
    def log(self, message: str, level: str = 'INFO'):
        """
        Log a message within the context.
        
        Parameters:
        -----------
        message : str
            Message to log
        level : str
            Log level
        """
        log_func = getattr(self.logger, level.lower())
        log_func(f"  {message}")


def log_parameter_summary(
    logger: logging.Logger,
    **kwargs
) -> None:
    """
    Log analysis parameters in a formatted way.
    
    Parameters:
    -----------
    logger : logging.Logger
        Logger instance
    **kwargs : Any
        Parameters to log
    """
    logger.info("Analysis Parameters:")
    logger.info("-" * 60)
    
    for key, value in kwargs.items():
        param_name = key.replace('_', ' ').title()
        
        if isinstance(value, (list, tuple)):
            logger.info(f"  {param_name}: {', '.join(map(str, value))}")
        elif isinstance(value, dict):
            logger.info(f"  {param_name}:")
            for k, v in value.items():
                logger.info(f"    - {k}: {v}")
        else:
            logger.info(f"  {param_name}: {value}")
    
    logger.info("-" * 60)


def log_results_summary(
    logger: logging.Logger,
    results: dict
) -> None:
    """
    Log analysis results in a formatted way.
    
    Parameters:
    -----------
    logger : logging.Logger
        Logger instance
    results : dict
        Results to log
    """
    logger.info("Analysis Results:")
    logger.info("=" * 60)
    
    for metric_name, metric_results in results.items():
        logger.info(f"\n{metric_name}:")
        logger.info("-" * 60)
        
        if isinstance(metric_results, dict):
            for key, value in metric_results.items():
                result_name = key.replace('_', ' ').title()
                
                if isinstance(value, float):
                    logger.info(f"  {result_name}: {value:.4f}")
                else:
                    logger.info(f"  {result_name}: {value}")
        else:
            logger.info(f"  {metric_results}")
    
    logger.info("=" * 60)
