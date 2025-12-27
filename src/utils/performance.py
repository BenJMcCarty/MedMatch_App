"""Performance monitoring utilities.

Provides decorators and helpers to monitor function execution time, log slow
operations, and collect basic system health metrics for diagnostics.
"""

import functools
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import pandas as pd
import psutil

# Use a module-level logger; avoid configuring logging at import time
perf_logger = logging.getLogger(__name__)

# Global performance metrics storage
_performance_metrics: Dict[str, Dict] = {}


def monitor_performance(slow_threshold: float = 1.0, log_memory: bool = False):
    """
    Decorator to monitor function performance and log slow operations.

    Args:
        slow_threshold (float): Threshold in seconds above which to log as slow
        log_memory (bool): Whether to log memory usage

    Returns:
        Callable: Decorated function with performance monitoring

    Example:
        @monitor_performance(slow_threshold=0.5, log_memory=True)
        def my_function():
            # Function implementation
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            func_name = f"{func.__module__}.{func.__name__}"
            start_time = time.time()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024 if log_memory else None

            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                # Log performance metrics
                _log_performance_metrics(
                    func_name, execution_time, start_memory, slow_threshold, log_memory, success=True
                )

                return result

            except Exception as e:
                execution_time = time.time() - start_time
                _log_performance_metrics(
                    func_name, execution_time, start_memory, slow_threshold, log_memory, success=False, error=str(e)
                )
                raise

        return wrapper

    return decorator


def _log_performance_metrics(
    func_name: str,
    execution_time: float,
    start_memory: Optional[float],
    slow_threshold: float,
    log_memory: bool,
    success: bool,
    error: Optional[str] = None,
):
    """Log performance metrics for a function execution."""

    # Store metrics
    if func_name not in _performance_metrics:
        _performance_metrics[func_name] = {
            "call_count": 0,
            "total_time": 0.0,
            "avg_time": 0.0,
            "max_time": 0.0,
            "error_count": 0,
            "last_call": None,
        }

    metrics = _performance_metrics[func_name]
    metrics["call_count"] += 1
    metrics["total_time"] += execution_time
    metrics["avg_time"] = metrics["total_time"] / metrics["call_count"]
    metrics["max_time"] = max(metrics["max_time"], execution_time)
    metrics["last_call"] = datetime.now().isoformat()

    if not success:
        metrics["error_count"] += 1

    # Log based on performance
    if not success:
        perf_logger.error(f"{func_name} failed after {execution_time:.3f}s: {error}")
    elif execution_time > slow_threshold:
        perf_logger.warning(f"SLOW: {func_name} took {execution_time:.3f}s (threshold: {slow_threshold}s)")
    else:
        perf_logger.debug(f"{func_name} completed in {execution_time:.3f}s")

    # Log memory usage if requested
    if log_memory and start_memory is not None:
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_diff = end_memory - start_memory
        if abs(memory_diff) > 10:  # Log if memory change > 10MB
            perf_logger.info(f"{func_name} memory change: {memory_diff:+.1f}MB (now: {end_memory:.1f}MB)")


class PerformanceTracker:
    """Track and analyze performance metrics across the application."""

    @staticmethod
    def get_performance_summary() -> pd.DataFrame:
        """
        Get a summary of performance metrics for all monitored functions.

        Returns:
            pd.DataFrame: Performance summary with columns:
                - function_name: Name of the function
                - call_count: Number of times called
                - avg_time: Average execution time
                - max_time: Maximum execution time
                - error_rate: Percentage of calls that resulted in errors
                - last_call: Timestamp of last call
        """
        if not _performance_metrics:
            return pd.DataFrame()

        summary_data = []
        for func_name, metrics in _performance_metrics.items():
            error_rate = (metrics["error_count"] / metrics["call_count"]) * 100
            summary_data.append(
                {
                    "function_name": func_name,
                    "call_count": metrics["call_count"],
                    "avg_time": round(metrics["avg_time"], 3),
                    "max_time": round(metrics["max_time"], 3),
                    "error_rate": round(error_rate, 1),
                    "last_call": metrics["last_call"],
                }
            )

        df = pd.DataFrame(summary_data)
        return df.sort_values("avg_time", ascending=False)

    @staticmethod
    def get_slow_functions(threshold: float = 1.0) -> pd.DataFrame:
        """
        Get functions that are consistently slow.

        Args:
            threshold (float): Time threshold in seconds

        Returns:
            pd.DataFrame: Slow functions with their metrics
        """
        summary = PerformanceTracker.get_performance_summary()
        if summary.empty:
            return summary

        return summary[summary["avg_time"] > threshold]

    @staticmethod
    def reset_metrics():
        """Reset all performance metrics."""
        _performance_metrics.clear()
        perf_logger.info("Performance metrics reset")

    @staticmethod
    def get_system_health() -> Dict[str, Any]:
        """
        Get current system health metrics.

        Returns:
            Dict[str, Any]: System health information
        """
        try:
            process = psutil.Process()
            return {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "memory_percent": process.memory_percent(),
                "disk_usage_percent": psutil.disk_usage("/").percent,
                "active_threads": process.num_threads(),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            perf_logger.error(f"Error getting system health: {e}")
            return {"error": str(e)}


class DataProcessingProfiler:
    """Profile data processing operations for optimization."""

    @staticmethod
    def profile_dataframe_operation(operation_name: str):
        """
        Decorator specifically for profiling pandas DataFrame operations.

        Args:
            operation_name (str): Name of the operation being profiled

        Example:
            @DataProcessingProfiler.profile_dataframe_operation("data_loading")
            def load_data():
                return pd.read_csv("large_file.csv")
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                start_time = time.time()
                start_memory = psutil.Process().memory_info().rss / 1024 / 1024

                result = func(*args, **kwargs)

                execution_time = time.time() - start_time
                end_memory = psutil.Process().memory_info().rss / 1024 / 1024
                memory_used = end_memory - start_memory

                # Log DataFrame-specific metrics
                if isinstance(result, pd.DataFrame):
                    rows, cols = result.shape
                    memory_per_row = memory_used / rows if rows > 0 else 0

                    perf_logger.info(
                        f"DataFrame Operation [{operation_name}]: "
                        f"{execution_time:.3f}s, {rows:,} rows, {cols} cols, "
                        f"{memory_used:.1f}MB ({memory_per_row:.3f}MB/row)"
                    )
                else:
                    perf_logger.info(f"Operation [{operation_name}]: {execution_time:.3f}s, {memory_used:.1f}MB")

                return result

            return wrapper

        return decorator

    @staticmethod
    def benchmark_distance_calculation(provider_count: int = 1000, iterations: int = 5) -> Dict[str, float]:
        """
        Benchmark distance calculation performance.

        Args:
            provider_count (int): Number of providers to simulate
            iterations (int): Number of iterations to run

        Returns:
            Dict[str, float]: Benchmark results
        """
        import numpy as np
        from geopy.distance import geodesic

        # Generate test data
        user_lat, user_lon = 40.7128, -74.0060  # New York City
        provider_lats = np.random.uniform(40.5, 40.9, provider_count)
        provider_lons = np.random.uniform(-74.3, -73.7, provider_count)

        results = []

        for i in range(iterations):
            start_time = time.time()

            # Simulate distance calculation
            distances = []
            for lat, lon in zip(provider_lats, provider_lons):
                distance = geodesic((user_lat, user_lon), (lat, lon)).miles
                distances.append(distance)

            execution_time = time.time() - start_time
            results.append(execution_time)

        avg_time = sum(results) / len(results)
        min_time = min(results)
        max_time = max(results)

        perf_logger.info(
            f"Distance Calculation Benchmark: {provider_count} providers, "
            f"avg: {avg_time:.3f}s, min: {min_time:.3f}s, max: {max_time:.3f}s"
        )

        return {
            "provider_count": provider_count,
            "iterations": iterations,
            "avg_time": avg_time,
            "min_time": min_time,
            "max_time": max_time,
            "providers_per_second": provider_count / avg_time,
        }


# Export main classes and functions
__all__ = ["monitor_performance", "PerformanceTracker", "DataProcessingProfiler"]
