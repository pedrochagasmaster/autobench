"""
Logger - Logging configuration and utilities.

Sets up structured logging for the benchmarking tool.
"""

import logging
import sys
import threading
from pathlib import Path
from datetime import datetime
from typing import Callable, List, Optional
from uuid import uuid4


NON_PUBLISHABLE_LOG_PREFIX = "autobench_NON_PUBLISHABLE_run_log_"
_QUARANTINE_HEADER = (
    "# NON-PUBLISHABLE AUTOBENCH RUN LOG\n"
    "# This diagnostic log belongs to a run whose output was not authorized\n"
    "# for publication. It may reference governed benchmark data.\n"
    "# Do not share, attach, or distribute this file.\n"
)


_privacy_gate_state = threading.local()
_privacy_gate_lock = threading.RLock()
_privacy_active_gates: dict[int, "PrivacyRunLogGate"] = {}
_privacy_downstream_call_handlers: Optional[
    Callable[[logging.Logger, logging.LogRecord], None]
] = None


def _privacy_gated_call_handlers(
    logger: logging.Logger,
    record: logging.LogRecord,
) -> None:
    """Capture run-thread records before any current or future handler."""
    with _privacy_gate_lock:
        gate = _privacy_active_gates.get(threading.get_ident())
        if gate is not None:
            gate._records.append((logger, record))
            return
        downstream = _privacy_downstream_call_handlers
    if downstream is not None:
        downstream(logger, record)


class DeferredFileHandler(logging.Handler):
    """Buffer records until a final privacy decision permits disk output."""

    def __init__(self, log_file: str) -> None:
        super().__init__(level=logging.DEBUG)
        self.log_file = log_file
        self._records: List[logging.LogRecord] = []
        self._finalized = False

    def emit(self, record: logging.LogRecord) -> None:
        if not self._finalized:
            self._records.append(record)

    def commit(self) -> str:
        """Write buffered records to the configured file exactly once."""
        if self._finalized:
            return self.log_file
        log_path = Path(self.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        target = logging.FileHandler(self.log_file, mode="w")
        target.setLevel(self.level)
        target.setFormatter(self.formatter)
        try:
            for record in self._records:
                target.handle(record)
        finally:
            target.close()
            self._records.clear()
            self._finalized = True
        return self.log_file

    def quarantine(self) -> Optional[str]:
        """Persist buffered records to a non-publishable file, exactly once.

        The intended log path is never created; diagnostics are preserved in
        a clearly marked quarantine file beside it instead of being dropped.
        """
        if self._finalized:
            return None
        self._finalized = True
        records = list(self._records)
        self._records.clear()
        if not records:
            return None
        quarantine_path = Path(self.log_file).parent / (
            f"{NON_PUBLISHABLE_LOG_PREFIX}{uuid4().hex}.log"
        )
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        quarantine_path.write_text(_QUARANTINE_HEADER, encoding="utf-8")
        target = logging.FileHandler(
            str(quarantine_path), mode="a", encoding="utf-8"
        )
        target.setLevel(self.level)
        target.setFormatter(self.formatter)
        try:
            for record in records:
                target.handle(record)
        finally:
            target.close()
        return str(quarantine_path)


def _deferred_handlers_for(logger: logging.Logger) -> List[DeferredFileHandler]:
    """Collect tool-owned deferred handlers reachable from a logger."""
    handlers: List[DeferredFileHandler] = []
    current: Optional[logging.Logger] = logger
    while current is not None:
        for handler in current.handlers:
            if isinstance(handler, DeferredFileHandler):
                handlers.append(handler)
        if not current.propagate:
            break
        current = current.parent
    return handlers


class PrivacyRunLogGate:
    """Temporarily buffer logger dispatch for one governed run thread."""

    def __init__(self) -> None:
        self._records: List[tuple[logging.Logger, logging.LogRecord]] = []
        self._finished = False
        self._started = False
        self._thread_id: Optional[int] = None

    def start(self) -> None:
        """Install run-thread capture before handler dispatch."""
        global _privacy_downstream_call_handlers
        if getattr(_privacy_gate_state, "active", False):
            raise RuntimeError(
                "Nested privacy-governed runs on the same thread are not supported"
            )
        thread_id = threading.get_ident()
        with _privacy_gate_lock:
            if not _privacy_active_gates:
                _privacy_downstream_call_handlers = (
                    logging.Logger.callHandlers
                )
                setattr(
                    logging.Logger,
                    "callHandlers",
                    _privacy_gated_call_handlers,
                )
            _privacy_active_gates[thread_id] = self
        _privacy_gate_state.active = True
        self._thread_id = thread_id
        self._started = True

    def finish(self, *, privacy_authorized: bool) -> None:
        """Restore logger dispatch and replay only an authorized run."""
        global _privacy_downstream_call_handlers
        if self._finished:
            return
        self._finished = True
        records: List[tuple[logging.Logger, logging.LogRecord]] = []
        downstream: Optional[
            Callable[[logging.Logger, logging.LogRecord], None]
        ] = None
        try:
            with _privacy_gate_lock:
                if self._thread_id is not None:
                    _privacy_active_gates.pop(self._thread_id, None)
                if not _privacy_active_gates:
                    downstream = _privacy_downstream_call_handlers
                    setattr(
                        logging.Logger,
                        "callHandlers",
                        downstream or logging.Logger.callHandlers,
                    )
                    _privacy_downstream_call_handlers = None
                else:
                    downstream = _privacy_downstream_call_handlers
            records = list(self._records)
            self._records.clear()
            if privacy_authorized:
                for logger, record in records:
                    try:
                        if downstream is not None:
                            downstream(logger, record)
                    except Exception:
                        # Logging must never alter analysis behavior.
                        pass
            else:
                # Unauthorized runs never reach console or caller-owned
                # handlers; route diagnostics only into tool-owned deferred
                # handlers so they can be quarantined rather than lost.
                for logger, record in records:
                    for handler in _deferred_handlers_for(logger):
                        try:
                            if record.levelno >= handler.level:
                                handler.handle(record)
                        except Exception:
                            pass
        finally:
            if self._started:
                _privacy_gate_state.active = False
                self._started = False
                self._thread_id = None


def finalize_deferred_logging(
    logger: logging.Logger,
    *,
    privacy_authorized: bool,
) -> Optional[str]:
    """Commit or quarantine tool-owned deferred file handlers.

    Returns the intended log path when authorized, or the quarantine file
    path when the run was denied and buffered diagnostics existed.
    """
    final_path: Optional[str] = None
    owners: List[logging.Logger] = []
    current: Optional[logging.Logger] = logger
    while current is not None:
        owners.append(current)
        current = current.parent
    for owner in owners:
        for handler in list(owner.handlers):
            if not isinstance(handler, DeferredFileHandler):
                continue
            owner.removeHandler(handler)
            if privacy_authorized:
                final_path = handler.commit()
            else:
                final_path = handler.quarantine() or final_path
            handler.close()
    return final_path


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


def setup_deferred_logging(
    log_level: str,
    log_file: str,
    *,
    console_output: bool = True,
) -> logging.Logger:
    """Configure normal logging with an authorization-gated file sink."""
    logger = setup_logging(
        log_level=log_level,
        log_file=None,
        console_output=console_output,
    )
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    deferred_handler = DeferredFileHandler(log_file)
    deferred_handler.setFormatter(formatter)
    logger.addHandler(deferred_handler)
    logger.info("Log file: %s", log_file)
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
