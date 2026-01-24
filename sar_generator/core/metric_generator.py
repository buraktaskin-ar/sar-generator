"""
Metrik Üretimi İçin Temel Sınıf

Bu modül, SAR log verilerindeki her bir metrik için değer üretimini sağlayan
temel sınıfı içerir. Tüm metrik üreticileri bu sınıftan türetilir.

Temel Konsept:
--------------
Her metrik değeri şu bileşenlerden oluşur:
1. Base Value (Temel Değer): Metriğin "normal" seviyesi
2. Trend (Eğilim): Zamanla değişen yavaş artış/azalış
3. Pattern (Desen): Günlük/haftalık tekrarlanan desenler
4. Noise (Gürültü): Gerçekçi rastgele dalgalanmalar
5. Correlation Effect (Korelasyon Etkisi): Diğer metriklerden gelen etkiler

Örnek:
------
CPU kullanımı = base(40%) + trend(+5%) + pattern(gece:-10%) + noise(±2%) + correlation(memory_etkisi)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import numpy as np


class MetricGenerator(ABC):
    """
    Tüm metrik üreticileri için soyut temel sınıf.

    Bu sınıf, bir metriğin nasıl üretileceğine dair genel yapıyı tanımlar.
    Her spesifik metrik (CPU, memory, disk I/O vb.) bu sınıftan türetilir
    ve kendi özel mantığını uygular.

    Attributes:
        name: Metrik adı (örn: "%usr", "kbmemused")
        base_value: Metriğin normal koşullardaki ortalama değeri
        min_value: Metriğin alabileceği minimum değer
        max_value: Metriğin alabileceği maksimum değer
        unit: Metriğin birimi (%, KB, count vb.)
        volatility: Metriğin değişkenliği (0.0-1.0, yüksek = daha değişken)
    """

    def __init__(
            self,
            name: str,
            base_value: float,
            min_value: float,
            max_value: float,
            unit: str = "",
            volatility: float = 0.1
    ):
        """
        MetricGenerator sınıfını başlatır.

        Args:
            name: Metrik adı
            base_value: Temel değer (normal koşullardaki ortalama)
            min_value: Minimum değer (metrik bu değerin altına düşemez)
            max_value: Maksimum değer (metrik bu değerin üstüne çıkamaz)
            unit: Birim (görüntüleme amaçlı)
            volatility: Değişkenlik katsayısı (0.0 = stabil, 1.0 = çok değişken)
        """
        self.name = name
        self.base_value = base_value
        self.min_value = min_value
        self.max_value = max_value
        self.unit = unit
        self.volatility = volatility

        # Dahili durum - trend takibi için
        self._current_trend_offset = 0.0
        self._trend_change_rate = 0.0

    def generate(
            self,
            timestamp: datetime,
            correlation_effects: Optional[Dict[str, float]] = None,
            scenario_modifier: Optional[float] = None
    ) -> float:
        """
        Belirli bir zaman noktası için metrik değeri üretir.

        Bu ana metod, bir metriğin değerini oluşturmak için tüm bileşenleri
        birleştirir: temel değer, trend, desenler, gürültü ve korelasyonlar.

        Args:
            timestamp: Veri noktasının zaman damgası
            correlation_effects: Diğer metriklerden gelen etkiler
                Örnek: {"cpu_effect": 0.15, "memory_pressure": -0.05}
            scenario_modifier: Anormallik senaryoları için çarpan (1.0 = normal)

        Returns:
            Üretilen metrik değeri (min_value ile max_value arasında sınırlandırılmış)
        """
        # 1. Temel değerden başla
        value = self.base_value

        # 2. Trend ekle (zaman içinde yavaş değişim)
        value += self._calculate_trend(timestamp)

        # 3. Zamansal desenleri uygula (günlük/haftalık döngüler)
        value += self._apply_temporal_patterns(timestamp)

        # 4. Gerçekçi gürültü ekle (rastgele dalgalanmalar)
        value += self._add_noise()

        # 5. Diğer metriklerden gelen etkileri uygula
        if correlation_effects:
            value += self._apply_correlation_effects(correlation_effects)

        # 6. Senaryo modifikasyonlarını uygula (örn: anormallikler)
        if scenario_modifier is not None:
            value *= scenario_modifier

        # 7. Değeri geçerli aralıkta sınırla
        value = self._clamp(value)

        return value

    def _calculate_trend(self, timestamp: datetime) -> float:
        """
        Metriğin zamanla değişen trend bileşenini hesaplar.

        Trend, bir metriğin uzun vadeli yavaş artış veya azalış eğilimidir.
        Örneğin, bir sunucuda disk kullanımı zamanla yavaşça artabilir.

        Trend değişimi düzgün (smooth) olmalıdır - ani sıçramalar olmamalı.
        Bu yüzden trend_change_rate kullanarak yavaş değişim sağlıyoruz.

        Args:
            timestamp: Mevcut zaman damgası

        Returns:
            Trend etkisi (pozitif veya negatif bir offset)
        """
        # Basit implementasyon: Şimdilik sabit trend
        # Gelişmiş versiyonda, zamanla değişen dinamik trendler eklenebilir
        return self._current_trend_offset

    @abstractmethod
    def _apply_temporal_patterns(self, timestamp: datetime) -> float:
        """
        Zamansal desenleri uygular (günlük/haftalık döngüler).

        Her metrik tipinin kendine özgü zamansal desenleri olabilir:
        - CPU kullanımı: Gündüz yüksek, gece düşük
        - Yedekleme I/O: Gece belirli saatlerde spike
        - Network trafiği: Hafta içi yüksek, hafta sonu düşük

        Bu metod alt sınıflarda uygulanmalıdır (abstract method).

        Args:
            timestamp: Mevcut zaman damgası

        Returns:
            Zamansal pattern etkisi (base_value'ya eklenecek offset)
        """
        pass

    def _add_noise(self) -> float:
        """
        Metriğe gerçekçi rastgele gürültü ekler.

        Gerçek dünyada hiçbir metrik tam sabit kalmaz. Küçük dalgalanmalar
        vardır. Bu gürültü, metriğin volatility değerine göre ölçeklenir.

        Gaussian (normal) dağılım kullanıyoruz çünkü doğal değişkenlikler
        genellikle bu dağılıma uyar.

        Returns:
            Rastgele gürültü değeri
        """
        # Standart sapma, base_value ve volatility'ye göre ölçeklenir
        std_dev = self.base_value * self.volatility * 0.1

        # Normal dağılımdan rastgele değer
        noise = np.random.normal(0, std_dev)

        return noise

    def _apply_correlation_effects(self, effects: Dict[str, float]) -> float:
        """
        Diğer metriklerden gelen korelasyon etkilerini toplar.

        Metrikler birbirini etkiler. Örneğin:
        - Yüksek CPU kullanımı → artan context switch sayısı
        - Yüksek memory kullanımı → artan page fault oranı
        - Yüksek disk I/O → artan %iowait

        Args:
            effects: Metrik adı -> etki miktarı dictionary'si

        Returns:
            Toplam korelasyon etkisi
        """
        total_effect = sum(effects.values())
        return total_effect

    def _clamp(self, value: float) -> float:
        """
        Değeri belirlenen minimum ve maksimum sınırlar içinde tutar.

        Metrikler fiziksel sınırlara sahiptir:
        - CPU %: 0-100 arasında
        - Memory kullanımı: 0 ile toplam RAM arasında
        - Disk I/O: Fiziksel disk hızı ile sınırlı

        Args:
            value: Sınırlanacak değer

        Returns:
            Sınırlandırılmış değer
        """
        return max(self.min_value, min(self.max_value, value))

    def set_trend(self, trend_offset: float, change_rate: float = 0.0):
        """
        Metriğin trend parametrelerini ayarlar.

        Bu metod, metriğin zamanla nasıl değişeceğini kontrol etmek için
        kullanılır. Örneğin, bir sunucuda disk doluluk oranının artmasını
        simüle etmek için pozitif bir trend offset verilebilir.

        Args:
            trend_offset: Mevcut trend offseti
            change_rate: Trend'in değişim hızı (her adımda ne kadar değişeceği)
        """
        self._current_trend_offset = trend_offset
        self._trend_change_rate = change_rate

    def update_trend(self):
        """
        Trend'i bir adım ilerletir.

        Her zaman adımında, trend yavaşça değişebilir. Bu metod, trend'in
        change_rate parametresine göre güncellenmesini sağlar.
        """
        self._current_trend_offset += self._trend_change_rate

    def get_metadata(self) -> Dict[str, Any]:
        """
        Metrik hakkında bilgi döndürür.

        Returns:
            Metrik metadata'sı içeren dictionary
        """
        return {
            "name": self.name,
            "base_value": self.base_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "unit": self.unit,
            "volatility": self.volatility,
            "current_trend": self._current_trend_offset
        }


class PercentageMetric(MetricGenerator):
    """
    Yüzde bazlı metrikler için özelleştirilmiş sınıf.

    CPU kullanımı, memory kullanımı gibi 0-100% arasında değişen
    metrikler için kullanılır.

    Bu sınıf, otomatik olarak min=0, max=100 sınırlarını uygular.
    """

    def __init__(
            self,
            name: str,
            base_value: float,
            volatility: float = 0.1
    ):
        """
        Yüzde metriği oluşturur.

        Args:
            name: Metrik adı
            base_value: Temel yüzde değeri (0-100)
            volatility: Değişkenlik katsayısı
        """
        super().__init__(
            name=name,
            base_value=base_value,
            min_value=0.0,
            max_value=100.0,
            unit="%",
            volatility=volatility
        )

    def _apply_temporal_patterns(self, timestamp: datetime) -> float:
        """
        Basit günlük desen: Gündüz artar, gece azalır.

        Bu basit implementasyon, saat bazlı sinüs dalgası kullanır.
        Daha gerçekçi desenler için alt sınıflarda override edilebilir.
        """
        hour = timestamp.hour

        # Sabah 9'da maksimum, gece 3'te minimum
        # Sinüs fonksiyonu ile yumuşak geçiş
        hour_offset = (hour - 9) * np.pi / 12
        pattern_effect = np.sin(hour_offset) * self.base_value * 0.2

        return pattern_effect


class CountMetric(MetricGenerator):
    """
    Sayısal metrikler için sınıf (proc/s, file-nr, vb.).

    Negatif olamayan, üst sınırı sistem kapasitesine bağlı olan
    metrikler için kullanılır.
    """

    def __init__(
            self,
            name: str,
            base_value: float,
            max_value: float,
            unit: str = "count",
            volatility: float = 0.15
    ):
        super().__init__(
            name=name,
            base_value=base_value,
            min_value=0.0,
            max_value=max_value,
            unit=unit,
            volatility=volatility
        )

    def _apply_temporal_patterns(self, timestamp: datetime) -> float:
        """
        Sayısal metrikler için temporal pattern.

        Genellikle iş yükü ile ilişkili, bu yüzden basit
        günlük desen uyguluyoruz.
        """
        hour = timestamp.hour

        # İş saatleri (9-17) daha yüksek
        if 9 <= hour <= 17:
            return self.base_value * 0.3
        else:
            return -self.base_value * 0.2


class ThroughputMetric(MetricGenerator):
    """
    Throughput (işlem hızı) metrikleri için sınıf.

    Disk I/O (MB/s), network (KB/s) gibi hız bazlı metrikler için.
    """

    def __init__(
            self,
            name: str,
            base_value: float,
            max_value: float,
            unit: str = "KB/s",
            volatility: float = 0.2
    ):
        super().__init__(
            name=name,
            base_value=base_value,
            min_value=0.0,
            max_value=max_value,
            unit=unit,
            volatility=volatility
        )

    def _apply_temporal_patterns(self, timestamp: datetime) -> float:
        """
        Throughput metrikleri için pattern.

        Network ve disk I/O genellikle burst (patlama) şeklinde
        gelir, o yüzden daha yüksek volatility kullanıyoruz.
        """
        hour = timestamp.hour
        weekday = timestamp.weekday()

        # Hafta içi vs hafta sonu farkı
        weekday_factor = 1.0 if weekday < 5 else 0.6

        # Gündüz vs gece farkı
        hour_offset = (hour - 14) * np.pi / 12
        hour_pattern = np.sin(hour_offset) * 0.3

        return self.base_value * weekday_factor * hour_pattern