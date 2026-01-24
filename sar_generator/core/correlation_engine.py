"""
Korelasyon Motoru (Correlation Engine)

Bu modül, sistem metriklerinin birbirleriyle nasıl etkileşime girdiğini yönetir.
Gerçek dünyada metrikler bağımsız değildir - bir metriğin değişmesi diğerlerini etkiler.

Temel Kavram:
-------------
Bir sistemde metrikler arasında nedensel ilişkiler vardır:
1. Doğrudan Korelasyonlar: CPU artar → Context switch artar
2. Ters Korelasyonlar: Memory artar → Free memory azalır
3. Gecikimli Etkiler: Disk I/O artar → 30 saniye sonra %iowait artar
4. Çoklu Bağımlılıklar: Network trafiği = func(disk_replication, user_activity, backups)

Örnek Korelasyonlar (OpenStack/CEPH ortamında):
-----------------------------------------------
- Yüksek %usr → Artan proc/s (process creation) → Artan cswch/s (context switches)
- Yüksek memory kullanımı → Azalan kbmemfree → Artan pgpgin/s (page-in operations)
- CEPH replication → Artan bread/s, bwrtn/s → Artan txkB/s (network transmit)
- Storage contention → Artan await, avgqu-sz → Artan %iowait
"""

from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import numpy as np


class CorrelationType(Enum):
    """
    Korelasyon tipleri.

    Metrikler arasındaki ilişki farklı şekillerde olabilir:
    - LINEAR: Doğrusal ilişki (bir artar, diğer de orantılı artar)
    - INVERSE: Ters ilişki (bir artar, diğer azalır)
    - LOGARITHMIC: Logaritmik ilişki (başlangıçta güçlü, sonra zayıflar)
    - THRESHOLD: Eşik bazlı (bir değer geçildiğinde etki başlar)
    """
    LINEAR = "linear"
    INVERSE = "inverse"
    LOGARITHMIC = "logarithmic"
    THRESHOLD = "threshold"


@dataclass
class CorrelationRule:
    """
    İki metrik arasındaki korelasyon kuralını tanımlar.

    Attributes:
        source_metric: Kaynak metrik adı (etkileyen)
        target_metric: Hedef metrik adı (etkilenen)
        correlation_type: Korelasyon tipi
        strength: Korelasyon gücü (0.0-1.0, 1.0 en güçlü)
        delay_steps: Etkinin kaç zaman adımı sonra görüneceği (0 = anında)
        threshold: Eşik değer (THRESHOLD tipi için)
        description: Korelasyonun açıklaması (debugging için)

    Örnek:
        # CPU artışı, context switch'leri artırır
        CorrelationRule(
            source_metric="%usr",
            target_metric="cswch/s",
            correlation_type=CorrelationType.LINEAR,
            strength=0.7,
            delay_steps=0,
            description="High CPU usage increases context switches"
        )
    """
    source_metric: str
    target_metric: str
    correlation_type: CorrelationType
    strength: float
    delay_steps: int = 0
    threshold: Optional[float] = None
    description: str = ""

    def __post_init__(self):
        """Parametreleri doğrular."""
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"Strength must be between 0.0 and 1.0, got {self.strength}")

        if self.delay_steps < 0:
            raise ValueError(f"Delay steps cannot be negative, got {self.delay_steps}")

        if self.correlation_type == CorrelationType.THRESHOLD and self.threshold is None:
            raise ValueError("Threshold correlation type requires a threshold value")


class CorrelationEngine:
    """
    Metrikler arası korelasyonları yöneten merkezi motor.

    Bu sınıf, hangi metriklerin hangi metrikleri nasıl etkilediğini
    bilir ve bu etkileri hesaplar.

    İki ana işlevi vardır:
    1. Korelasyon kurallarını kaydetmek ve yönetmek
    2. Mevcut metrik değerlerine göre korelasyon etkilerini hesaplamak

    Kullanım:
    ---------
    ```python
    engine = CorrelationEngine()

    # CPU -> Context Switch korelasyonu ekle
    engine.add_rule(
        source_metric="%usr",
        target_metric="cswch/s",
        correlation_type=CorrelationType.LINEAR,
        strength=0.8
    )

    # Mevcut metriklere göre etkileri hesapla
    current_values = {"%usr": 85.0}
    effects = engine.calculate_effects("cswch/s", current_values)
    # effects = {"cpu_effect": 1200.5}  # cswch/s için ek değer
    ```
    """

    def __init__(self):
        """CorrelationEngine'i başlatır."""
        # Korelasyon kurallarını saklar: target_metric -> [rules]
        self._rules: Dict[str, List[CorrelationRule]] = {}

        # Gecikimli etkileri saklar: (target, step_offset) -> value
        # Bazı etkiler hemen görünmez, birkaç adım sonra etkiler
        self._delayed_effects: Dict[Tuple[str, int], float] = {}

        # Mevcut zaman adımı (delay tracking için)
        self._current_step = 0

    def add_rule(
            self,
            source_metric: str,
            target_metric: str,
            correlation_type: CorrelationType,
            strength: float,
            delay_steps: int = 0,
            threshold: Optional[float] = None,
            description: str = ""
    ):
        """
        Yeni bir korelasyon kuralı ekler.

        Args:
            source_metric: Kaynak metrik adı
            target_metric: Hedef metrik adı
            correlation_type: Korelasyon tipi
            strength: Korelasyon gücü (0.0-1.0)
            delay_steps: Gecikme (kaç adım sonra etkili olacak)
            threshold: Eşik değer (THRESHOLD tipi için)
            description: Açıklama
        """
        rule = CorrelationRule(
            source_metric=source_metric,
            target_metric=target_metric,
            correlation_type=correlation_type,
            strength=strength,
            delay_steps=delay_steps,
            threshold=threshold,
            description=description
        )

        # Target metrik için kural listesini oluştur/güncelle
        if target_metric not in self._rules:
            self._rules[target_metric] = []

        self._rules[target_metric].append(rule)

    def calculate_effects(
            self,
            target_metric: str,
            current_values: Dict[str, float],
            base_value: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Bir metrik için tüm korelasyon etkilerini hesaplar.

        Bu metod, hedef metriği etkileyen tüm kaynak metrikleri kontrol eder
        ve her birinin etkisini hesaplayarak toplar.

        Args:
            target_metric: Etkileri hesaplanacak metrik
            current_values: Mevcut tüm metrik değerleri
            base_value: Hedef metriğin temel değeri (bazı hesaplamalar için)

        Returns:
            Etki kaynağı -> etki miktarı dictionary'si
            Örnek: {"cpu_effect": 15.2, "memory_pressure": -5.3}
        """
        effects = {}

        # Bu metriği etkileyen kurallar var mı?
        if target_metric not in self._rules:
            return effects

        # Her kural için etkiyi hesapla
        for rule in self._rules[target_metric]:
            # Kaynak metrik değeri mevcut mu?
            if rule.source_metric not in current_values:
                continue

            source_value = current_values[rule.source_metric]

            # Korelasyon tipine göre etki hesapla
            effect = self._calculate_single_effect(
                rule=rule,
                source_value=source_value,
                base_value=base_value
            )

            # Gecikme varsa, gelecek bir adım için sakla
            if rule.delay_steps > 0:
                future_step = self._current_step + rule.delay_steps
                key = (target_metric, future_step)
                self._delayed_effects[key] = effect
            else:
                # Anında etkiyi kaydet
                effect_key = f"{rule.source_metric}_effect"
                effects[effect_key] = effect

        # Geçmiş adımlardan gelen gecikimli etkileri ekle
        effects.update(self._get_delayed_effects(target_metric))

        return effects

    def _calculate_single_effect(
            self,
            rule: CorrelationRule,
            source_value: float,
            base_value: Optional[float] = None
    ) -> float:
        """
        Tek bir korelasyon kuralının etkisini hesaplar.

        Args:
            rule: Korelasyon kuralı
            source_value: Kaynak metriğin mevcut değeri
            base_value: Hedef metriğin temel değeri

        Returns:
            Hesaplanan etki miktarı
        """
        if rule.correlation_type == CorrelationType.LINEAR:
            # Doğrusal korelasyon: etki = kaynak_değer * güç
            # Kaynak değer ne kadar yüksekse, etki o kadar büyük
            effect = source_value * rule.strength

        elif rule.correlation_type == CorrelationType.INVERSE:
            # Ters korelasyon: kaynak artar, hedef azalır
            # base_value kullanarak orantılı azalış hesapla
            if base_value is None:
                base_value = 100.0  # Default fallback
            effect = -source_value * rule.strength * (base_value / 100.0)

        elif rule.correlation_type == CorrelationType.LOGARITHMIC:
            # Logaritmik korelasyon: Başta güçlü, sonra zayıflar
            # Yüksek değerlerde doyum noktasına ulaşır
            if source_value > 0:
                effect = np.log1p(source_value) * rule.strength * 10
            else:
                effect = 0.0

        elif rule.correlation_type == CorrelationType.THRESHOLD:
            # Eşik bazlı: Belirli değer aşılınca etki başlar
            if source_value >= rule.threshold:
                # Eşik aşıldı, tam etki ver
                excess = source_value - rule.threshold
                effect = excess * rule.strength
            else:
                # Eşik aşılmadı, etki yok
                effect = 0.0

        else:
            effect = 0.0

        return effect

    def _get_delayed_effects(self, target_metric: str) -> Dict[str, float]:
        """
        Geçmiş adımlardan gelen gecikimli etkileri getirir.

        Args:
            target_metric: Hedef metrik

        Returns:
            Gecikimli etkiler dictionary'si
        """
        effects = {}
        keys_to_remove = []

        # Bu adım için bekleyen gecikimli etkileri bul
        for (metric, step), effect in self._delayed_effects.items():
            if metric == target_metric and step == self._current_step:
                effect_key = f"delayed_effect_{step}"
                effects[effect_key] = effect
                keys_to_remove.append((metric, step))

        # Kullanılan gecikimli etkileri temizle
        for key in keys_to_remove:
            del self._delayed_effects[key]

        return effects

    def advance_step(self):
        """
        Zaman adımını bir ileri alır.

        Bu metod her yeni zaman noktası üretildiğinde çağrılmalıdır.
        Gecikimli etkilerin doğru zamanda uygulanması için gereklidir.
        """
        self._current_step += 1

        # Çok eski gecikimli etkileri temizle (memory leak önleme)
        max_age = 1000  # 1000 adımdan eski etkileri sil
        cutoff_step = self._current_step - max_age

        keys_to_remove = [
            key for key in self._delayed_effects.keys()
            if key[1] < cutoff_step
        ]

        for key in keys_to_remove:
            del self._delayed_effects[key]

    def get_rules_for_metric(self, target_metric: str) -> List[CorrelationRule]:
        """
        Belirli bir metriği etkileyen tüm kuralları döndürür.

        Args:
            target_metric: Hedef metrik adı

        Returns:
            Korelasyon kuralları listesi
        """
        return self._rules.get(target_metric, [])

    def get_all_rules(self) -> Dict[str, List[CorrelationRule]]:
        """
        Tüm korelasyon kurallarını döndürür.

        Returns:
            Hedef metrik -> kurallar dictionary'si
        """
        return self._rules.copy()

    def clear_rules(self):
        """Tüm korelasyon kurallarını temizler."""
        self._rules.clear()
        self._delayed_effects.clear()

    def get_statistics(self) -> Dict[str, any]:
        """
        Motor hakkında istatistiksel bilgi döndürür.

        Returns:
            İstatistik bilgileri
        """
        total_rules = sum(len(rules) for rules in self._rules.values())

        return {
            "total_rules": total_rules,
            "affected_metrics": len(self._rules),
            "current_step": self._current_step,
            "pending_delayed_effects": len(self._delayed_effects)
        }


def create_default_correlations() -> CorrelationEngine:
    """
    Telco Cloud ortamı için varsayılan korelasyon kurallarını oluşturur.

    Bu fonksiyon, OpenStack ve CEPH ortamlarında gözlemlenen tipik
    metrik korelasyonlarını içeren önceden yapılandırılmış bir motor döndürür.

    Returns:
        Varsayılan kurallarla yapılandırılmış CorrelationEngine

    Örnek Kullanım:
    ---------------
    ```python
    engine = create_default_correlations()
    # Artık engine CPU, memory, disk ve network korelasyonlarını biliyor
    ```
    """
    engine = CorrelationEngine()

    # ============== CPU İlişkili Korelasyonlar ==============

    # Yüksek CPU kullanımı -> Artan context switch
    engine.add_rule(
        source_metric="%usr",
        target_metric="cswch/s",
        correlation_type=CorrelationType.LINEAR,
        strength=0.75,
        description="High CPU user time increases context switches"
    )

    # Yüksek CPU system time -> Artan proc/s (process creation)
    engine.add_rule(
        source_metric="%sys",
        target_metric="proc/s",
        correlation_type=CorrelationType.LINEAR,
        strength=0.6,
        description="High system CPU increases process creation"
    )

    # Yüksek CPU -> Azalan idle
    engine.add_rule(
        source_metric="%usr",
        target_metric="%idle",
        correlation_type=CorrelationType.INVERSE,
        strength=0.9,
        description="High CPU usage reduces idle percentage"
    )

    # ============== Memory İlişkili Korelasyonlar ==============

    # Yüksek memory kullanımı -> Azalan free memory
    engine.add_rule(
        source_metric="kbmemused",
        target_metric="kbmemfree",
        correlation_type=CorrelationType.INVERSE,
        strength=1.0,
        description="Memory usage inversely affects free memory"
    )

    # Düşük free memory -> Artan page-in (disk'ten memory'ye veri çekme)
    engine.add_rule(
        source_metric="kbmemfree",
        target_metric="pgpgin/s",
        correlation_type=CorrelationType.THRESHOLD,
        strength=0.8,
        threshold=1000000,  # 1GB altında eşik
        description="Low free memory triggers page-in operations"
    )

    # Yüksek page faults -> Artan CPU system time
    engine.add_rule(
        source_metric="fault/s",
        target_metric="%sys",
        correlation_type=CorrelationType.LINEAR,
        strength=0.3,
        description="Page faults increase system CPU usage"
    )

    # ============== Disk I/O İlişkili Korelasyonlar ==============

    # Yüksek disk read -> Artan %iowait (gecikimli etki)
    engine.add_rule(
        source_metric="bread/s",
        target_metric="%iowait",
        correlation_type=CorrelationType.LOGARITHMIC,
        strength=0.7,
        delay_steps=2,  # 2 adım sonra etkili
        description="High disk reads increase iowait with delay"
    )

    # Yüksek disk write -> Artan %iowait
    engine.add_rule(
        source_metric="bwrtn/s",
        target_metric="%iowait",
        correlation_type=CorrelationType.LOGARITHMIC,
        strength=0.7,
        delay_steps=2,
        description="High disk writes increase iowait with delay"
    )

    # Yüksek I/O queue -> Artan await (disk latency)
    engine.add_rule(
        source_metric="avgqu-sz",
        target_metric="await",
        correlation_type=CorrelationType.LINEAR,
        strength=0.85,
        description="High I/O queue size increases wait time"
    )

    # ============== CEPH Storage İlişkili Korelasyonlar ==============

    # CEPH replication: Disk write -> Network transmit
    engine.add_rule(
        source_metric="bwrtn/s",
        target_metric="txkB/s",
        correlation_type=CorrelationType.LINEAR,
        strength=0.6,
        delay_steps=1,
        description="CEPH replication: disk writes trigger network traffic"
    )

    # CEPH recovery: Disk read -> Network transmit
    engine.add_rule(
        source_metric="bread/s",
        target_metric="txkB/s",
        correlation_type=CorrelationType.LINEAR,
        strength=0.5,
        description="CEPH recovery: disk reads trigger network traffic"
    )

    # ============== Network İlişkili Korelasyonlar ==============

    # Yüksek network receive -> Artan CPU soft interrupt
    engine.add_rule(
        source_metric="rxkB/s",
        target_metric="%soft",
        correlation_type=CorrelationType.LINEAR,
        strength=0.4,
        description="High network receive increases soft interrupt CPU"
    )

    # Yüksek network transmit -> Artan CPU soft interrupt
    engine.add_rule(
        source_metric="txkB/s",
        target_metric="%soft",
        correlation_type=CorrelationType.LINEAR,
        strength=0.4,
        description="High network transmit increases soft interrupt CPU"
    )

    # Network errors -> Artan retransmissions
    engine.add_rule(
        source_metric="rxerr/s",
        target_metric="retrans/s",
        correlation_type=CorrelationType.LINEAR,
        strength=0.7,
        description="Network receive errors increase retransmissions"
    )

    return engine