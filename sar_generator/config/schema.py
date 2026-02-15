"""
SAR Generator Configuration Schema
===================================

Bu modül, YAML/JSON konfigürasyon dosyalarının validasyonu ve
tip dönüşümlerini sağlar. Pydantic v2 modelleri kullanılır.

Temel Yapı:
-----------
GeneratorConfig (ana konfigürasyon)
├── SimulationConfig (zaman ayarları)
├── List[NodeConfig] (node grupları)
│   └── NodeType (compute, ceph_storage, control_plane, network)
├── List[ScenarioConfig] (anomali senaryoları - opsiyonel)
│   └── AnomalyType + SeverityLevel
├── CorrelationConfig (korelasyon ayarları)
├── PatternConfig (zamansal desen ayarları)
└── OutputConfig (çıktı formatı ayarları)

Örnek YAML:
-----------
```yaml
simulation:
  start_time: "2024-01-01 00:00:00"
  end_time: "2024-01-02 00:00:00"
  interval_seconds: 300

nodes:
  - type: compute
    count: 3
    base_load: 0.6

output:
  format: csv
  output_dir: "./output"
```
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================
# Enum Tanımlamaları
# ============================================================

class NodeType(str, Enum):
    """
    Telco Cloud node tipleri.

    Her tip, farklı donanım konfigürasyonu ve yazılım yüküne sahiptir:
    - COMPUTE: VM'leri çalıştıran Nova hypervisor node'ları
    - CEPH_STORAGE: Dağıtık storage kümesindeki OSD node'ları
    - CONTROL_PLANE: OpenStack API ve yönetim servisleri
    - NETWORK: Neutron/OVS ağ servisleri
    """
    COMPUTE = "compute"
    CEPH_STORAGE = "ceph_storage"
    CONTROL_PLANE = "control_plane"
    NETWORK = "network"


class AnomalyType(str, Enum):
    """
    Simüle edilebilecek anomali tipleri.

    Her anomali tipi, belirli metriklerde karakteristik değişiklikler yaratır.
    Örneğin STORAGE_CONTENTION, disk I/O metrikleri ve %iowait'i etkiler.
    """
    CPU_SPIKE = "cpu_spike"
    MEMORY_LEAK = "memory_leak"
    STORAGE_CONTENTION = "storage_contention"
    NETWORK_SATURATION = "network_saturation"
    CPU_STEAL_SPIKE = "cpu_steal_spike"
    CEPH_RECOVERY = "ceph_recovery"
    CASCADING_FAILURE = "cascading_failure"
    NOISY_NEIGHBOR = "noisy_neighbor"


class SeverityLevel(str, Enum):
    """
    Anomali şiddet seviyeleri.

    Şiddet seviyesi, anomali senaryosundaki metrik sapma büyüklüğünü belirler:
    - LOW: %20-40 sapma (fark edilebilir ama kritik değil)
    - MEDIUM: %40-70 sapma (alarm eşiklerini tetikleyebilir)
    - HIGH: %70-100 sapma (ciddi performans etkisi)
    - CRITICAL: %100+ sapma (sistem limitlerine yaklaşma)
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OutputFormat(str, Enum):
    """Desteklenen çıktı formatları"""
    CSV = "csv"
    JSON = "json"
    SAR_TEXT = "sar_text"
    ALL = "all"


class DataQualityLevel(str, Enum):
    """
    Veri kalite seviyeleri.

    Korelasyon gücü, noise seviyesi ve pattern detayını kontrol eder:
    - LOW: Daha fazla noise, basit korelasyonlar (hızlı üretim)
    - MEDIUM: Dengeli (varsayılan)
    - HIGH: Az noise, güçlü korelasyonlar, detaylı patterns (gerçekçi)
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================================
# Alt Konfigürasyon Modelleri
# ============================================================

class SimulationConfig(BaseModel):
    """
    Simülasyon zaman ayarları.

    Üretilecek verinin zaman aralığını ve örnekleme sıklığını belirler.
    SAR'ın varsayılan örnekleme aralığı 10 dakikadır (600 saniye),
    ancak Telco Cloud ortamlarında genellikle 5 dakika (300 saniye) kullanılır.
    """
    start_time: datetime = Field(
        ...,
        description="Simülasyon başlangıç zamanı (YYYY-MM-DD HH:MM:SS)"
    )
    end_time: datetime = Field(
        ...,
        description="Simülasyon bitiş zamanı (YYYY-MM-DD HH:MM:SS)"
    )
    interval_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Örnekleme aralığı (saniye). SAR varsayılanı: 600, Telco: 300"
    )

    @field_validator('start_time', 'end_time', mode='before')
    @classmethod
    def parse_datetime(cls, v):
        """String formatındaki datetime'ı parse eder. Birden fazla formatı destekler."""
        if isinstance(v, str):
            # Desteklenen formatlar (sırayla denenir)
            formats = [
                "%Y-%m-%d %H:%M:%S",      # "2024-01-01 00:00:00"
                "%Y-%m-%dT%H:%M:%S",      # "2024-01-01T00:00:00" (ISO)
                "%Y-%m-%d %H:%M",          # "2024-01-01 00:00"
                "%Y-%m-%d",                # "2024-01-01" (gece yarısı kabul edilir)
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
            raise ValueError(
                f"Geçersiz tarih formatı: '{v}'. "
                f"Beklenen format: 'YYYY-MM-DD HH:MM:SS' veya ISO format"
            )
        return v

    @model_validator(mode='after')
    def validate_time_range(self):
        """Bitiş zamanının başlangıçtan sonra olduğunu doğrular."""
        if self.end_time <= self.start_time:
            raise ValueError(
                f"end_time ({self.end_time}) start_time'dan ({self.start_time}) "
                f"büyük olmalı"
            )
        return self

    @property
    def duration_seconds(self) -> int:
        """Toplam simülasyon süresi (saniye)."""
        return int((self.end_time - self.start_time).total_seconds())

    @property
    def total_samples(self) -> int:
        """Toplam üretilecek örnek sayısı."""
        return self.duration_seconds // self.interval_seconds


class NodeConfig(BaseModel):
    """
    Tek bir node grubu konfigürasyonu.

    Bir Telco Cloud ortamında her tip node'dan birden fazla bulunur.
    Bu model, aynı tipteki node grubunun ortak parametrelerini tanımlar.

    Örnek:
        3 adet compute node, base_load=0.6 (yüksek yük)
        2 adet ceph_storage node, base_load=0.5 (normal yük)
    """
    type: NodeType = Field(
        ...,
        description="Node tipi (compute, ceph_storage, control_plane, network)"
    )
    count: int = Field(
        default=1,
        ge=1,
        le=1000,
        description="Bu tipten kaç node oluşturulacağı"
    )
    base_load: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Temel yük seviyesi (0.0=boşta, 0.5=normal, 1.0=tam kapasite)"
    )
    name_prefix: Optional[str] = Field(
        default=None,
        description="Node isimlendirme ön eki (None ise tip adından türetilir)"
    )

    @model_validator(mode='after')
    def set_default_prefix(self):
        """Name prefix belirtilmemişse node tipinden türetir."""
        if self.name_prefix is None:
            # "ceph_storage" -> "ceph", "control_plane" -> "control"
            self.name_prefix = self.type.value.split('_')[0]
        return self


class ScenarioConfig(BaseModel):
    """
    Belirli bir zamanda tetiklenecek anomali senaryosu.

    Senaryolar, normal veri üretiminin üzerine eklenen anormallik
    periyotlarıdır. Her senaryo belirli bir zamanda başlar, belirli
    bir süre devam eder ve belirli şiddette etki yaratır.

    Örnek:
        Saat 14:00'te başlayan, 2 saat sürecek, orta şiddette
        storage contention senaryosu.
    """
    type: AnomalyType = Field(
        ...,
        description="Anomali tipi"
    )
    start_offset_minutes: int = Field(
        ...,
        ge=0,
        description="Simülasyon başlangıcından itibaren kaç dakika sonra başlayacağı"
    )
    duration_minutes: int = Field(
        ...,
        gt=0,
        le=1440,
        description="Senaryo süresi (dakika, max 24 saat)"
    )
    severity: SeverityLevel = Field(
        default=SeverityLevel.MEDIUM,
        description="Şiddet seviyesi"
    )
    affected_node_types: Optional[List[NodeType]] = Field(
        default=None,
        description="Etkilenecek node tipleri (None ise tüm uygun tipler)"
    )
    affected_node_ids: Optional[List[str]] = Field(
        default=None,
        description="Etkilenecek spesifik node ID'leri (None ise tümü)"
    )
    ramp_up_minutes: int = Field(
        default=5,
        ge=0,
        description="Anomalinin kademeli olarak başlama süresi (dakika)"
    )
    ramp_down_minutes: int = Field(
        default=5,
        ge=0,
        description="Anomalinin kademeli olarak bitme süresi (dakika)"
    )
    description: str = Field(
        default="",
        description="Senaryo açıklaması (opsiyonel)"
    )


class CorrelationConfig(BaseModel):
    """
    Metrikler arası korelasyon ayarları.

    Korelasyon gücü ve gecikme parametrelerini global olarak ayarlar.
    Varsayılan değerler, gerçek Telco Cloud gözlemlerine dayanır.
    """
    enabled: bool = Field(
        default=True,
        description="Korelasyonları etkinleştir/devre dışı bırak"
    )
    global_strength_multiplier: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Tüm korelasyon güçlerini çarpan faktör (1.0=varsayılan)"
    )
    max_delay_steps: int = Field(
        default=10,
        ge=0,
        le=100,
        description="Gecikimli etkilerin maksimum adım sayısı"
    )


class PatternConfig(BaseModel):
    """
    Zamansal desen ayarları.

    Günlük ve haftalık döngülerin parametrelerini kontrol eder.
    Telco Cloud'da belirgin iş saatleri ve hafta sonu farkları gözlemlenir.
    """
    diurnal_enabled: bool = Field(
        default=True,
        description="Günlük döngü (gece/gündüz farkı) etkin mi?"
    )
    weekly_enabled: bool = Field(
        default=True,
        description="Haftalık döngü (hafta içi/sonu farkı) etkin mi?"
    )
    business_hours_start: int = Field(
        default=9,
        ge=0,
        le=23,
        description="İş saatleri başlangıcı (saat, 24-saat formatı)"
    )
    business_hours_end: int = Field(
        default=18,
        ge=1,
        le=24,
        description="İş saatleri bitişi (saat, 24-saat formatı)"
    )
    peak_hour: int = Field(
        default=14,
        ge=0,
        le=23,
        description="Günlük pik yük saati"
    )
    night_reduction_factor: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Gece saatlerinde yük azalma oranı (0.0=sıfır yük, 1.0=gündüzle aynı)"
    )
    weekend_reduction_factor: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Hafta sonu yük azalma oranı"
    )
    backup_window_start: int = Field(
        default=2,
        ge=0,
        le=23,
        description="Yedekleme penceresi başlangıç saati"
    )
    backup_window_end: int = Field(
        default=4,
        ge=0,
        le=23,
        description="Yedekleme penceresi bitiş saati"
    )
    backup_io_multiplier: float = Field(
        default=3.0,
        ge=1.0,
        le=10.0,
        description="Yedekleme sırasında I/O çarpanı"
    )

    @model_validator(mode='after')
    def validate_hours(self):
        """İş saatleri ve backup penceresi tutarlılığını doğrular."""
        if self.business_hours_end <= self.business_hours_start:
            raise ValueError(
                f"business_hours_end ({self.business_hours_end}) "
                f"business_hours_start'tan ({self.business_hours_start}) büyük olmalı"
            )
        return self


class OutputConfig(BaseModel):
    """
    Çıktı formatı ve dosya yolu ayarları.

    Üretilen verinin hangi formatta ve nereye kaydedileceğini belirler.
    """
    format: OutputFormat = Field(
        default=OutputFormat.CSV,
        description="Çıktı formatı"
    )
    output_dir: str = Field(
        default="./output",
        description="Çıktı dosyalarının kaydedileceği dizin"
    )
    file_prefix: str = Field(
        default="sar_data",
        description="Çıktı dosya adı ön eki"
    )
    separate_by_node: bool = Field(
        default=True,
        description="Her node için ayrı dosya oluştur"
    )
    include_metadata: bool = Field(
        default=True,
        description="Metadata bilgilerini çıktıya ekle"
    )
    csv_separator: str = Field(
        default=";",
        description="CSV ayırıcı karakter (SAR varsayılanı: ';')"
    )
    decimal_places: int = Field(
        default=2,
        ge=0,
        le=6,
        description="Ondalık basamak sayısı"
    )


# ============================================================
# Ana Konfigürasyon Modeli
# ============================================================

class GeneratorConfig(BaseModel):
    """
    SAR Generator ana konfigürasyon modeli.

    Bu model, tüm alt konfigürasyonları bir araya getirir ve
    YAML/JSON dosyasından yüklenen verinin tam validasyonunu yapar.

    Kullanım:
    ---------
    ```python
    # YAML'dan yükleme
    config = GeneratorConfig.from_yaml("config.yaml")

    # Dictionary'den oluşturma
    config = GeneratorConfig(**config_dict)

    # Programatik oluşturma
    config = GeneratorConfig(
        simulation=SimulationConfig(
            start_time="2024-01-01 00:00:00",
            end_time="2024-01-02 00:00:00"
        ),
        nodes=[
            NodeConfig(type="compute", count=3, base_load=0.6),
            NodeConfig(type="ceph_storage", count=2, base_load=0.5)
        ]
    )
    ```
    """
    simulation: SimulationConfig = Field(
        ...,
        description="Simülasyon zaman ayarları"
    )
    nodes: List[NodeConfig] = Field(
        ...,
        min_length=1,
        description="Node grupları konfigürasyonu (en az 1 tane olmalı)"
    )
    scenarios: List[ScenarioConfig] = Field(
        default_factory=list,
        description="Anomali senaryoları (opsiyonel)"
    )
    correlation: CorrelationConfig = Field(
        default_factory=CorrelationConfig,
        description="Korelasyon ayarları"
    )
    patterns: PatternConfig = Field(
        default_factory=PatternConfig,
        description="Zamansal desen ayarları"
    )
    output: OutputConfig = Field(
        default_factory=OutputConfig,
        description="Çıktı ayarları"
    )
    quality: DataQualityLevel = Field(
        default=DataQualityLevel.MEDIUM,
        description="Veri kalite seviyesi"
    )
    random_seed: Optional[int] = Field(
        default=None,
        description="Rastgele sayı üretici tohumu (tekrarlanabilirlik için)"
    )

    @model_validator(mode='after')
    def validate_scenarios_timing(self):
        """Senaryoların simülasyon süresi içinde olduğunu doğrular."""
        sim_duration_minutes = self.simulation.duration_seconds / 60

        for i, scenario in enumerate(self.scenarios):
            scenario_end = scenario.start_offset_minutes + scenario.duration_minutes
            if scenario_end > sim_duration_minutes:
                raise ValueError(
                    f"Senaryo {i} ({scenario.type.value}): "
                    f"Bitiş zamanı ({scenario_end} dk) simülasyon süresini "
                    f"({sim_duration_minutes:.0f} dk) aşıyor"
                )
        return self

    @property
    def total_node_count(self) -> int:
        """Toplam node sayısı."""
        return sum(node.count for node in self.nodes)

    @property
    def total_data_points(self) -> int:
        """Toplam üretilecek veri noktası sayısı (tüm node'lar için)."""
        return self.simulation.total_samples * self.total_node_count

    def get_node_ids(self) -> List[str]:
        """
        Tüm node ID'lerini üretir.

        Returns:
            Node ID listesi. Örnek: ["compute-01", "compute-02", "ceph-01"]
        """
        ids = []
        for node_config in self.nodes:
            for i in range(1, node_config.count + 1):
                node_id = f"{node_config.name_prefix}-{i:02d}"
                ids.append(node_id)
        return ids

    def get_summary(self) -> Dict[str, Any]:
        """
        Konfigürasyon özetini döndürür.

        Returns:
            Özet bilgiler dictionary'si
        """
        return {
            "simulation_duration": f"{self.simulation.duration_seconds / 3600:.1f} saat",
            "interval": f"{self.simulation.interval_seconds} saniye",
            "total_samples_per_node": self.simulation.total_samples,
            "node_groups": len(self.nodes),
            "total_nodes": self.total_node_count,
            "total_data_points": self.total_data_points,
            "scenarios": len(self.scenarios),
            "output_format": self.output.format.value,
            "quality": self.quality.value,
            "node_ids": self.get_node_ids()
        }

    @classmethod
    def from_yaml(cls, yaml_path: Union[str, Path]) -> "GeneratorConfig":
        """
        YAML dosyasından konfigürasyon yükler.

        Args:
            yaml_path: YAML dosyasının yolu

        Returns:
            Validate edilmiş GeneratorConfig nesnesi

        Raises:
            FileNotFoundError: Dosya bulunamazsa
            ValueError: Konfigürasyon geçersizse
        """
        import yaml

        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Konfigürasyon dosyası bulunamadı: {yaml_path}")

        with open(yaml_path, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)

        if config_dict is None:
            raise ValueError(f"Boş konfigürasyon dosyası: {yaml_path}")

        return cls(**config_dict)

    def to_yaml(self, yaml_path: Union[str, Path]) -> None:
        """
        Konfigürasyonu YAML dosyasına kaydeder.

        Args:
            yaml_path: Hedef YAML dosyasının yolu
        """
        import yaml

        yaml_path = Path(yaml_path)
        yaml_path.parent.mkdir(parents=True, exist_ok=True)

        # Pydantic modelini dict'e dönüştür
        config_dict = self.model_dump(mode='json')

        # datetime objelerini string'e çevir
        if 'simulation' in config_dict:
            sim = config_dict['simulation']
            if isinstance(sim.get('start_time'), datetime):
                sim['start_time'] = sim['start_time'].strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(sim.get('end_time'), datetime):
                sim['end_time'] = sim['end_time'].strftime("%Y-%m-%d %H:%M:%S")

        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(
                config_dict,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )

    @classmethod
    def create_default(cls) -> "GeneratorConfig":
        """
        Varsayılan bir Telco Cloud konfigürasyonu oluşturur.

        Tipik bir telco cloud ortamını temsil eden varsayılan değerlerle
        hızlıca başlamak için kullanılır.

        Returns:
            Varsayılan konfigürasyon
        """
        return cls(
            simulation=SimulationConfig(
                start_time="2024-01-01 00:00:00",
                end_time="2024-01-02 00:00:00",
                interval_seconds=300
            ),
            nodes=[
                NodeConfig(type=NodeType.COMPUTE, count=3, base_load=0.6),
                NodeConfig(type=NodeType.CEPH_STORAGE, count=2, base_load=0.5),
                NodeConfig(type=NodeType.CONTROL_PLANE, count=2, base_load=0.4),
                NodeConfig(type=NodeType.NETWORK, count=2, base_load=0.5),
            ],
            output=OutputConfig(
                format=OutputFormat.CSV,
                output_dir="./output"
            )
        )