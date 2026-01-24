"""
Base Node Sınıfı

Bu modül, tüm node tiplerinin (Compute, CEPH, Control, Network) türeyeceği
temel sınıfı içerir. BaseNode, ortak davranışları ve standart interface'i tanımlar.

Neden BaseNode Gerekli?
-----------------------
1. Kod Tekrarını Önler: Tüm node'larda ortak olan kod burada yazılır
2. Tutarlılık Sağlar: Her node tipi aynı metodlara sahip olur
3. Tip Güvenliği: Python type hints ile doğru kullanım garantilenir
4. Genişletilebilirlik: Yeni node tipi eklemek kolaydır

Mimarisi:
---------
BaseNode (abstract)
    ├── ComputeNode (VM'leri çalıştıran node)
    ├── CephNode (Storage node)
    ├── ControlNode (OpenStack control services)
    └── NetworkNode (Network services)

Her alt sınıf kendi özel metriklerini tanımlar ama hepsi
aynı interface'i kullanır.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..core.metric_generator import MetricGenerator
from ..core.correlation_engine import CorrelationEngine


class BaseNode(ABC):
    """
    Tüm node tipleri için soyut temel sınıf.

    Bu sınıf, bir node'un sahip olması gereken temel özellikleri ve
    metodları tanımlar. Doğrudan kullanılmaz, sadece alt sınıflar
    türetilir.

    Ortak Özellikler:
    ----------------
    - node_id: Benzersiz tanımlayıcı
    - node_type: Node tipi (compute, ceph, control, network)
    - base_load: Temel yük seviyesi (0.0-1.0)
    - correlation_engine: Metrikler arası korelasyon motoru
    - metrics: Tüm metrik üreticileri

    Zorunlu Metodlar (Alt Sınıflarda Uygulanmalı):
    ----------------------------------------------
    - _initialize_metrics(): Node'a özel metrikleri tanımlar
    - _get_node_type(): Node tipini döndürür

    Örnek Kullanım:
    ---------------
    BaseNode doğrudan kullanılmaz, sadece türetme için:

    ```python
    class MyCustomNode(BaseNode):
        def _initialize_metrics(self):
            # Bu node'a özel metrikleri tanımla
            self.metrics["%cpu"] = PercentageMetric(...)

        def _get_node_type(self) -> str:
            return "custom"

    # Artık kullanabiliriz
    node = MyCustomNode(node_id="custom-01", base_load=0.5)
    data = node.generate_metrics(datetime.now())
    ```
    """

    def __init__(
            self,
            node_id: str,
            base_load: float = 0.5,
            correlation_engine: Optional[CorrelationEngine] = None
    ):
        """
        BaseNode'u başlatır.

        Bu constructor tüm node tiplerinde ortak olan işlemleri yapar:
        - Parametreleri doğrular ve saklar
        - Correlation engine'i ayarlar
        - Metrik dictionary'sini oluşturur
        - Alt sınıfın _initialize_metrics() metodunu çağırır

        Args:
            node_id: Node'un benzersiz tanımlayıcısı
                Format önerisi: "{type}-{number}" örn: "compute-01"
            base_load: Temel yük seviyesi (0.0-1.0)
                0.0 = Boşta/minimum yük
                0.5 = Normal/ortalama yük
                1.0 = Tam kapasite/maksimum yük
            correlation_engine: Korelasyon motoru (None ise varsayılan kullanılır)

        Raises:
            ValueError: node_id boş ise veya base_load aralık dışında ise
        """
        # Parametreleri doğrula
        if not node_id or not isinstance(node_id, str):
            raise ValueError("node_id must be a non-empty string")

        if not 0.0 <= base_load <= 1.0:
            raise ValueError(f"base_load must be between 0.0 and 1.0, got {base_load}")

        # Temel özellikleri sakla
        self.node_id = node_id
        self.base_load = base_load

        # Correlation engine'i ayarla
        # Alt sınıf kendi engine'ini verebilir veya varsayılanı kullanabiliriz
        if correlation_engine is None:
            from ..core.correlation_engine import create_default_correlations
            self.correlation_engine = create_default_correlations()
        else:
            self.correlation_engine = correlation_engine

        # Metrik dictionary'sini oluştur
        # Alt sınıflar bunu _initialize_metrics() içinde dolduracak
        self.metrics: Dict[str, MetricGenerator] = {}

        # İstatistik için sayaçlar
        self._generation_count = 0
        self._last_generation_time: Optional[datetime] = None

        # Alt sınıfın metriklerini başlat
        # Bu abstract metod, alt sınıfta uygulanmalı
        self._initialize_metrics()

        # Metriklerin başlatıldığını doğrula
        if not self.metrics:
            raise RuntimeError(
                f"{self.__class__.__name__} must initialize at least one metric "
                f"in _initialize_metrics()"
            )

    @abstractmethod
    def _initialize_metrics(self):
        """
        Node'a özel metrikleri tanımlar.

        Bu metod alt sınıflarda uygulanmalıdır. Alt sınıf, kendi
        metriklerini oluşturup self.metrics dictionary'sine eklemelidir.

        Örnek:
        ------
        ```python
        def _initialize_metrics(self):
            # CPU metrikleri ekle
            self.metrics["%usr"] = PercentageMetric(
                name="%usr",
                base_value=40.0,
                volatility=0.15
            )

            # Memory metrikleri ekle
            self.metrics["kbmemused"] = CountMetric(
                name="kbmemused",
                base_value=80000000,
                max_value=128000000,
                unit="KB"
            )
            # ... daha fazla metrik
        ```

        Raises:
            NotImplementedError: Alt sınıf bu metodu uygulamazsa
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _initialize_metrics()"
        )

    @abstractmethod
    def _get_node_type(self) -> str:
        """
        Node tipini döndürür.

        Bu metod alt sınıflarda uygulanmalıdır. Node'un tipini
        belirten bir string döndürmelidir.

        Returns:
            Node tipi: "compute", "ceph", "control", veya "network"

        Örnek:
        ------
        ```python
        def _get_node_type(self) -> str:
            return "compute"
        ```
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _get_node_type()"
        )

    def generate_metrics(
            self,
            timestamp: datetime,
            scenario_modifier: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Belirli bir zaman noktası için tüm metrikleri üretir.

        Bu metod BaseNode seviyesinde temel yapıyı sağlar. Alt sınıflar
        gerekirse override edebilir ancak genellikle gerek yoktur çünkü
        metrikler _initialize_metrics()'te tanımlandığında bu metod
        otomatik olarak çalışır.

        Metod şu adımları izler:
        1. Sonuç dictionary'sini hazırla (timestamp, hostname vb.)
        2. Her metrik için değer üret
        3. Korelasyonları uygula
        4. Sonucu döndür

        Args:
            timestamp: Veri noktasının zaman damgası
            scenario_modifier: Anormallik senaryoları için modifier
                Örnek: {"%usr": 1.5, "await": 2.0}

        Returns:
            Metrik adı -> değer dictionary'si
            Her zaman "DateTime" ve "hostname" alanlarını içerir

        Örnek Dönüş Değeri:
        -------------------
        {
            "DateTime": "2024-01-01 12:00:00",
            "hostname": "compute-01",
            "%usr": 45.3,
            "%sys": 8.2,
            "kbmemused": 80234567,
            ...
        }
        """
        # İstatistik güncelle
        self._generation_count += 1
        self._last_generation_time = timestamp

        # Sonuç dictionary'si - her node için standart alanlar
        result = {
            "DateTime": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": self.node_id,
            "node_type": self._get_node_type()
        }

        # Mevcut metrik değerlerini sakla (korelasyon için)
        current_values: Dict[str, float] = {}

        # Her metrik için değer üret
        # Metrikler sırayla üretilir (bazıları diğerlerine bağımlı olabilir)
        for metric_name, metric_generator in self.metrics.items():
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

            # Sonuç ve mevcut değerlere ekle
            result[metric_name] = value
            current_values[metric_name] = value

        # Korelasyon motorunu bir adım ilerlet
        # Gecikimli etkilerin doğru zamanda uygulanması için gerekli
        self.correlation_engine.advance_step()

        return result

    def get_metric_names(self) -> List[str]:
        """
        Node'un ürettiği tüm metrik adlarını döndürür.

        Bu metod, hangi metriklerin mevcut olduğunu öğrenmek için
        kullanılır. CSV başlıkları oluşturmak, doğrulama yapmak vb.
        için faydalıdır.

        Returns:
            Metrik adları listesi

        Örnek:
        ------
        ```python
        node = ComputeNode("compute-01")
        metrics = node.get_metric_names()
        # metrics = ["%usr", "%sys", "kbmemused", ...]
        ```
        """
        return list(self.metrics.keys())

    def get_metric(self, metric_name: str) -> Optional[MetricGenerator]:
        """
        Belirli bir metrik üreticiyi döndürür.

        Bu metod, bir metriğin özelliklerini incelemek veya
        manuel olarak değer üretmek için kullanılabilir.

        Args:
            metric_name: Metrik adı

        Returns:
            MetricGenerator nesnesi veya None (metrik yoksa)

        Örnek:
        ------
        ```python
        node = ComputeNode("compute-01")
        cpu_metric = node.get_metric("%usr")
        if cpu_metric:
            print(f"Base value: {cpu_metric.base_value}")
        ```
        """
        return self.metrics.get(metric_name)

    def update_base_load(self, new_load: float):
        """
        Node'un temel yük seviyesini günceller.

        Bu metod, node'un yükünü dinamik olarak değiştirmek için
        kullanılır. Ancak DİKKAT: Sadece base_load değişkenini günceller,
        mevcut metriklerin base_value'larını otomatik güncellemez.

        Metriklerin base_value'larını güncellemek için _initialize_metrics()
        yeniden çağrılmalı veya her metriğin base_value'su manuel
        güncellenmelidir.

        Args:
            new_load: Yeni yük seviyesi (0.0-1.0)

        Raises:
            ValueError: new_load aralık dışında ise

        Not:
        ----
        Gelecek versiyonda, bu metod metrikleri de otomatik
        güncelleyebilir. Şimdilik dikkatli kullanılmalı.
        """
        if not 0.0 <= new_load <= 1.0:
            raise ValueError(f"new_load must be between 0.0 and 1.0, got {new_load}")

        self.base_load = new_load

        # TODO: Metriklerin base_value'larını da güncelle
        # Şimdilik sadece uyarı yazdır
        print(f"Warning: base_load updated to {new_load}, but metric base values "
              f"are not automatically recalculated. Consider reinitializing metrics.")

    def get_node_info(self) -> Dict[str, Any]:
        """
        Node hakkında detaylı bilgi döndürür.

        Bu metod, node'un mevcut durumu, yapılandırması ve
        istatistikleri hakkında bilgi sağlar.

        Returns:
            Node bilgileri dictionary'si

        Örnek Dönüş:
        ------------
        {
            "node_id": "compute-01",
            "node_type": "compute",
            "base_load": 0.6,
            "total_metrics": 42,
            "metric_names": ["%usr", "%sys", ...],
            "generation_count": 1440,
            "last_generation": "2024-01-01 23:59:00",
            "correlation_stats": {...}
        }
        """
        info = {
            "node_id": self.node_id,
            "node_type": self._get_node_type(),
            "base_load": self.base_load,
            "total_metrics": len(self.metrics),
            "metric_names": self.get_metric_names(),
            "generation_count": self._generation_count
        }

        # Son üretim zamanı varsa ekle
        if self._last_generation_time:
            info["last_generation"] = self._last_generation_time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        # Correlation engine istatistiklerini ekle
        info["correlation_stats"] = self.correlation_engine.get_statistics()

        return info

    def reset_statistics(self):
        """
        İstatistik sayaçlarını sıfırlar.

        Bu metod, generation_count ve last_generation_time gibi
        istatistik bilgilerini sıfırlar. Node'un metriklerini
        veya yapılandırmasını etkilemez.
        """
        self._generation_count = 0
        self._last_generation_time = None

    def __repr__(self) -> str:
        """
        Node'un string temsilini döndürür.

        Debugging ve logging için faydalıdır.

        Returns:
            Node'u tanımlayan string
        """
        return (
            f"{self.__class__.__name__}(node_id='{self.node_id}', "
            f"node_type='{self._get_node_type()}', "
            f"base_load={self.base_load:.2f}, "
            f"metrics={len(self.metrics)})"
        )

    def __str__(self) -> str:
        """
        Node'un okunabilir string temsilini döndürür.

        Returns:
            Kullanıcı dostu açıklama
        """
        return (
            f"{self._get_node_type().upper()} Node '{self.node_id}' "
            f"(load: {self.base_load:.0%}, metrics: {len(self.metrics)})"
        )