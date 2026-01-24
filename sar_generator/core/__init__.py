"""
Core Module - SAR Generator Ana Motor

Bu modül, SAR veri üretiminin temel bileşenlerini içerir:
- MetricGenerator: Metrik değer üretimi
- CorrelationEngine: Metrikler arası korelasyonlar
"""

from .metric_generator import (
    MetricGenerator,
    PercentageMetric,
    CountMetric,
    ThroughputMetric
)

from .correlation_engine import (
    CorrelationEngine,
    CorrelationType,
    CorrelationRule,
    create_default_correlations
)

__all__ = [
    "MetricGenerator",
    "PercentageMetric",
    "CountMetric",
    "ThroughputMetric",
    "CorrelationEngine",
    "CorrelationType",
    "CorrelationRule",
    "create_default_correlations"
]