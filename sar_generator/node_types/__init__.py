"""
Node Types Module - Farklı Node Tipleri

Bu modül, farklı OpenStack/CEPH node tiplerinin implementasyonlarını içerir:
- BaseNode: Tüm node'ların türediği temel sınıf
- ComputeNode: VM'leri çalıştıran compute node
"""

from .base_node import BaseNode
from .compute_node import ComputeNode

__all__ = [
    "BaseNode",
    "ComputeNode"
]