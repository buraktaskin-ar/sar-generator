"""
Compute Node Metrik Üretici

Bu modül, OpenStack compute node'larının (Nova hypervisor) davranışını simüle eder.
Compute node'lar sanal makineleri (VM) çalıştıran fiziksel sunuculardır.

Compute Node Özellikleri:
-------------------------
- Yüksek CPU kullanımı (%usr): VM'ler sürekli işlem yapar
- Orta-yüksek memory kullanımı: VM'lerin RAM ihtiyacı
- %steal metriği önemli: Hypervisor overhead'i gösterir
- Düşük disk I/O: VM'ler genellikle CEPH storage kullanır (network üzerinden)
- Network trafiği: VM network aktivitesi + CEPH storage trafiği

Tipik Metrik Değerleri (Normal Koşullarda):
-------------------------------------------
- %usr: 40-60% (VM'lerin CPU kullanımı)
- %sys: 5-15% (kernel işlemleri)
- %steal: 1-5% (hypervisor overhead, yüksek olması sorun işareti)
- %iowait: 2-8% (genellikle düşük, CEPH kullanıldığı için)
- Memory kullanımı: 70-85% (VM'lere ayrılmış)
- Context switches: Yüksek (çok VM çalıştığı için)
- Network: Orta-yüksek (CEPH + VM trafiği)
"""

from typing import Dict, List, Optional
from datetime import datetime
import numpy as np

from .base_node import BaseNode
from ..core.metric_generator import (
    MetricGenerator,
    PercentageMetric,
    CountMetric,
    ThroughputMetric
)
from ..core.correlation_engine import CorrelationEngine


class ComputeNode(BaseNode):
    """
    OpenStack Compute Node için metrik üretici sınıf.

    Bu sınıf, bir compute node'un tüm sistem metriklerini üretir.
    Her metrik tipi için uygun generator oluşturur ve bunları
    correlation engine ile koordine eder.

    Attributes:
        node_id: Node'un benzersiz tanımlayıcısı (örn: "compute-01")
        base_load: Temel yük seviyesi (0.0-1.0, 0.5 = %50 yük)
        correlation_engine: Metrikler arası korelasyon motoru
        metrics: Tüm metrik üreticileri dictionary'si

    Kullanım:
    ---------
    ```python
    # Compute node oluştur
    node = ComputeNode(node_id="compute-01", base_load=0.6)

    # Belirli bir zaman için veri üret
    timestamp = datetime(2024, 1, 1, 12, 0, 0)
    data = node.generate_metrics(timestamp)

    # data = {
    #     "DateTime": "2024-01-01 12:00:00",
    #     "%usr": 45.3,
    #     "%sys": 8.2,
    #     "kbmemused": 65432123,
    #     ...
    # }
    ```
    """

    def __init__(
            self,
            node_id: str,
            base_load: float = 0.5,
            correlation_engine: Optional[CorrelationEngine] = None
    ):
        """
        ComputeNode sınıfını başlatır.

        Args:
            node_id: Node tanımlayıcısı
            base_load: Temel yük seviyesi (0.0-1.0)
                0.3 = Düşük yük (az VM)
                0.5 = Normal yük
                0.7 = Yüksek yük (çok VM)
                0.9 = Neredeyse tam kapasite
            correlation_engine: Korelasyon motoru (None ise varsayılan kullanılır)
        """
        # BaseNode'un constructor'ını çağır
        # Bu, ortak özellikleri başlatacak ve _initialize_metrics() çağıracak
        super().__init__(
            node_id=node_id,
            base_load=base_load,
            correlation_engine=correlation_engine
        )

    def _get_node_type(self) -> str:
        """Node tipini döndürür."""
        return "compute"

    def _initialize_metrics(self):
        """
        Compute node için tüm metrik üreticileri oluşturur.

        Bu metod, bir compute node'un sahip olduğu tüm sistem metriklerini
        tanımlar. Her metrik için uygun base value, min/max sınırlar ve
        volatility değerleri belirlenir.

        Metrikler gruplar halinde organize edilir:
        1. CPU metrikleri
        2. Memory metrikleri
        3. Disk I/O metrikleri
        4. Network metrikleri
        5. System metrikleri
        """

        # ============== CPU METRİKLERİ ==============
        # Compute node'da CPU kullanımı genellikle yüksektir çünkü
        # birçok VM çalışmaktadır. base_load parametresine göre ölçeklenir.

        # %usr: User space CPU kullanımı (VM'lerin kullandığı CPU)
        # Compute node'un en önemli metriği - VM'ler ne kadar çalışıyor?
        self.metrics["%usr"] = PercentageMetric(
            name="%usr",
            base_value=40.0 * self.base_load + 20.0,  # base_load=0.5 için %40
            volatility=0.15  # Orta volatility - VM yükleri değişken
        )

        # %sys: System/kernel CPU kullanımı
        # Hypervisor overhead, system calls, kernel işlemleri
        self.metrics["%sys"] = PercentageMetric(
            name="%sys",
            base_value=8.0 * self.base_load + 3.0,
            volatility=0.1
        )

        # %iowait: Disk I/O beklerken harcanan CPU
        # Compute node'da genellikle DÜŞÜK (CEPH storage network üzerinden)
        # Ancak local disk kullanılıyorsa artabilir
        self.metrics["%iowait"] = PercentageMetric(
            name="%iowait",
            base_value=3.0 + 2.0 * self.base_load,
            volatility=0.2  # Yüksek volatility - burst I/O olabilir
        )

        # %steal: Hypervisor tarafından çalınan CPU
        # ÖNEMLİ: Compute node için kritik metrik
        # Yüksek %steal = overcommitment problemi veya noisy neighbor
        self.metrics["%steal"] = PercentageMetric(
            name="%steal",
            base_value=2.0 * self.base_load,
            volatility=0.15
        )

        # %idle: Boş CPU
        # Diğer CPU metriklerinin toplamını 100'den çıkararak hesaplanır
        # Ancak correlation engine bunu otomatik yapacak
        self.metrics["%idle"] = PercentageMetric(
            name="%idle",
            base_value=100.0 - (40.0 * self.base_load + 20.0) -
                       (8.0 * self.base_load + 3.0) -
                       (3.0 + 2.0 * self.base_load) -
                       (2.0 * self.base_load),
            volatility=0.1
        )

        # %soft: Soft interrupt CPU kullanımı
        # Network packet processing için önemli
        self.metrics["%soft"] = PercentageMetric(
            name="%soft",
            base_value=1.5 * self.base_load,
            volatility=0.2
        )

        # %irq: Hardware interrupt CPU
        self.metrics["%irq"] = PercentageMetric(
            name="%irq",
            base_value=0.5,
            volatility=0.1
        )

        # ============== PROCESS & SCHEDULING METRİKLERİ ==============

        # proc/s: Saniyede yaratılan process sayısı
        # Compute node'da orta seviye - VM'ler içinde process'ler yaratılır
        self.metrics["proc/s"] = CountMetric(
            name="proc/s",
            base_value=50 * self.base_load + 20,
            max_value=500,
            unit="count/s",
            volatility=0.2
        )

        # cswch/s: Context switch sayısı
        # ÇOK YÜKSEK olması normaldir - birçok VM, her biri kendi thread'leri
        self.metrics["cswch/s"] = CountMetric(
            name="cswch/s",
            base_value=5000 * self.base_load + 2000,
            max_value=50000,
            unit="count/s",
            volatility=0.15
        )

        # runq-sz: Run queue size (çalışmayı bekleyen process sayısı)
        # Yüksek olması CPU contention gösterir
        self.metrics["runq-sz"] = CountMetric(
            name="runq-sz",
            base_value=3.0 * self.base_load,
            max_value=100,
            unit="count",
            volatility=0.25
        )

        # ============== MEMORY METRİKLERİ ==============
        # Compute node'da memory kullanımı yüksektir
        # VM'lere allocation yapıldığı için genellikle %70-85 kullanılır

        # Örnek: 128GB RAM'li bir compute node varsayalım
        total_memory_kb = 128 * 1024 * 1024  # 128GB in KB

        # kbmemused: Kullanılan memory (KB)
        used_memory_base = total_memory_kb * (0.7 + 0.15 * self.base_load)
        self.metrics["kbmemused"] = CountMetric(
            name="kbmemused",
            base_value=used_memory_base,
            max_value=total_memory_kb,
            unit="KB",
            volatility=0.05  # Memory kullanımı genellikle stabil
        )

        # kbmemfree: Boş memory (KB)
        # Correlation engine bunu kbmemused'dan hesaplayacak
        self.metrics["kbmemfree"] = CountMetric(
            name="kbmemfree",
            base_value=total_memory_kb - used_memory_base,
            max_value=total_memory_kb,
            unit="KB",
            volatility=0.05
        )

        # %memused: Memory kullanım yüzdesi
        self.metrics["%memused"] = PercentageMetric(
            name="%memused",
            base_value=70.0 + 15.0 * self.base_load,
            volatility=0.05
        )

        # kbcached: Cache memory
        # OS, disk I/O performansı için cache yapar
        self.metrics["kbcached"] = CountMetric(
            name="kbcached",
            base_value=total_memory_kb * 0.1,
            max_value=total_memory_kb * 0.3,
            unit="KB",
            volatility=0.1
        )

        # ============== PAGING METRİKLERİ ==============
        # Compute node'da paging düşük olmalı (yeterli RAM var)
        # Yüksek paging = problem (memory pressure)

        # pgpgin/s: Page-in rate (disk'ten memory'ye)
        self.metrics["pgpgin/s"] = CountMetric(
            name="pgpgin/s",
            base_value=100 * self.base_load,
            max_value=10000,
            unit="pages/s",
            volatility=0.3
        )

        # pgpgout/s: Page-out rate (memory'den disk'e)
        self.metrics["pgpgout/s"] = CountMetric(
            name="pgpgout/s",
            base_value=50 * self.base_load,
            max_value=5000,
            unit="pages/s",
            volatility=0.3
        )

        # fault/s: Page fault rate
        self.metrics["fault/s"] = CountMetric(
            name="fault/s",
            base_value=1000 * self.base_load + 500,
            max_value=50000,
            unit="faults/s",
            volatility=0.2
        )

        # ============== DISK I/O METRİKLERİ ==============
        # Compute node genellikle CEPH kullanır, bu yüzden local disk I/O DÜŞÜK
        # Ancak VM image cache, logs için bazı local I/O olur

        # tps: Transactions per second (total I/O operations)
        self.metrics["tps"] = CountMetric(
            name="tps",
            base_value=100 * self.base_load + 50,
            max_value=5000,
            unit="ops/s",
            volatility=0.25
        )

        # bread/s: Blocks read per second
        self.metrics["bread/s"] = ThroughputMetric(
            name="bread/s",
            base_value=500 * self.base_load + 200,
            max_value=100000,
            unit="blocks/s",
            volatility=0.3
        )

        # bwrtn/s: Blocks written per second
        self.metrics["bwrtn/s"] = ThroughputMetric(
            name="bwrtn/s",
            base_value=800 * self.base_load + 300,
            max_value=100000,
            unit="blocks/s",
            volatility=0.3
        )

        # await: Average I/O wait time (ms)
        # Düşük olmalı - yüksek olması disk contention gösterir
        self.metrics["await"] = CountMetric(
            name="await",
            base_value=5.0 * self.base_load + 2.0,
            max_value=100,
            unit="ms",
            volatility=0.2
        )

        # avgqu-sz: Average queue size
        self.metrics["avgqu-sz"] = CountMetric(
            name="avgqu-sz",
            base_value=1.0 * self.base_load,
            max_value=20,
            unit="count",
            volatility=0.25
        )

        # %util: Disk utilization
        self.metrics["%util"] = PercentageMetric(
            name="%util",
            base_value=20.0 * self.base_load + 10.0,
            volatility=0.2
        )

        # ============== NETWORK METRİKLERİ ==============
        # Compute node'da network trafiği önemli:
        # 1. VM'lerin network trafiği
        # 2. CEPH storage trafiği (volume I/O network üzerinden)

        # rxkB/s: Network receive throughput
        # VM incoming traffic + CEPH reads
        self.metrics["rxkB/s"] = ThroughputMetric(
            name="rxkB/s",
            base_value=5000 * self.base_load + 2000,
            max_value=1000000,  # 1GB/s = ~1,000,000 KB/s
            unit="KB/s",
            volatility=0.3
        )

        # txkB/s: Network transmit throughput
        # VM outgoing traffic + CEPH writes
        self.metrics["txkB/s"] = ThroughputMetric(
            name="txkB/s",
            base_value=6000 * self.base_load + 2500,
            max_value=1000000,
            unit="KB/s",
            volatility=0.3
        )

        # rxpck/s: Packets received per second
        self.metrics["rxpck/s"] = CountMetric(
            name="rxpck/s",
            base_value=3000 * self.base_load + 1000,
            max_value=100000,
            unit="packets/s",
            volatility=0.25
        )

        # txpck/s: Packets transmitted per second
        self.metrics["txpck/s"] = CountMetric(
            name="txpck/s",
            base_value=3500 * self.base_load + 1200,
            max_value=100000,
            unit="packets/s",
            volatility=0.25
        )

        # rxerr/s, txerr/s: Network errors
        # Normalde ÇOK DÜŞÜK olmalı
        self.metrics["rxerr/s"] = CountMetric(
            name="rxerr/s",
            base_value=0.1,
            max_value=100,
            unit="errors/s",
            volatility=0.5  # Yüksek volatility - nadir ama burst olabilir
        )

        self.metrics["txerr/s"] = CountMetric(
            name="txerr/s",
            base_value=0.1,
            max_value=100,
            unit="errors/s",
            volatility=0.5
        )

        # ============== LOAD AVERAGE ==============
        # System load average - kaç process CPU bekliyor

        # ldavg-1: 1-minute load average
        # Genellikle CPU core sayısına yakın olmalı
        # Örnek: 32 core sistem için 16-24 arası normal
        self.metrics["ldavg-1"] = CountMetric(
            name="ldavg-1",
            base_value=16.0 * self.base_load + 8.0,
            max_value=64,
            unit="load",
            volatility=0.15
        )

        # ldavg-5: 5-minute load average
        self.metrics["ldavg-5"] = CountMetric(
            name="ldavg-5",
            base_value=15.0 * self.base_load + 7.0,
            max_value=64,
            unit="load",
            volatility=0.1
        )

        # ldavg-15: 15-minute load average
        self.metrics["ldavg-15"] = CountMetric(
            name="ldavg-15",
            base_value=14.0 * self.base_load + 6.0,
            max_value=64,
            unit="load",
            volatility=0.08
        )

    def _generate_single_metric(
            self,
            metric_name: str,
            timestamp: datetime,
            current_values: Dict[str, float],
            scenario_modifier: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Tek bir metrik için değer üretir (korelasyonlarla birlikte).

        Args:
            metric_name: Üretilecek metrik adı
            timestamp: Zaman damgası
            current_values: Şimdiye kadar üretilen metrik değerleri
            scenario_modifier: Senaryo modifikatörleri

        Returns:
            Üretilen metrik değeri
        """
        if metric_name not in self.metrics:
            return 0.0

        metric_generator = self.metrics[metric_name]

        # Bu metrik için korelasyon etkilerini hesapla
        correlation_effects = self.correlation_engine.calculate_effects(
            target_metric=metric_name,
            current_values=current_values,
            base_value=metric_generator.base_value
        )

        # Senaryo modifikatörünü al
        modifier = None
        if scenario_modifier and metric_name in scenario_modifier:
            modifier = scenario_modifier[metric_name]

        # Metriği üret
        value = metric_generator.generate(
            timestamp=timestamp,
            correlation_effects=correlation_effects,
            scenario_modifier=modifier
        )

        return value