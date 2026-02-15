"""
Diurnal (Günlük) Pattern Generator
====================================

Bu modül, 24 saatlik döngüde tekrar eden zamansal desenleri üretir.
Telco Cloud ortamlarında gözlemlenen tipik günlük pattern'ler:

1. Gece Quiet Period (00:00-06:00): Minimum yük, sadece background jobs
2. Sabah Ramp-Up (06:00-09:00): Kademeli yük artışı
3. Business Hours (09:00-18:00): Yüksek ve stabil yük
4. Peak Hour (genellikle 14:00): Günün en yoğun saati
5. Akşam Ramp-Down (18:00-22:00): Kademeli azalma
6. Backup Window (02:00-04:00): Disk I/O spike'ı

Pattern Hesaplama Mantığı:
--------------------------
Basit sinüs yerine, gerçek datacenter yük profili kullanılır.
Her saat için bir "yük faktörü" (0.0-1.0) hesaplanır ve bu faktör
metriğin base_value'su ile çarpılarak pattern etkisi belirlenir.

Smooth geçişler için sigmoid interpolation kullanılır —
ani sıçramalar yerine yumuşak artış/azalış sağlar.
"""

from datetime import datetime
from typing import Optional
import numpy as np


class DiurnalPattern:
    """
    Günlük (24 saatlik) döngü deseni üretici.

    PatternConfig'teki parametreleri kullanarak her zaman noktası için
    bir yük faktörü hesaplar. Bu faktör, metriğin base_value'su ile
    çarpılarak gerçek pattern etkisini verir.

    Attributes:
        business_hours_start: İş saatleri başlangıcı (varsayılan 9)
        business_hours_end: İş saatleri bitişi (varsayılan 18)
        peak_hour: Günlük pik yük saati (varsayılan 14)
        night_reduction: Gece yük azalma faktörü (varsayılan 0.4)
        backup_start: Backup penceresi başlangıcı (varsayılan 2)
        backup_end: Backup penceresi bitişi (varsayılan 4)
        backup_io_multiplier: Backup sırasında I/O çarpanı (varsayılan 3.0)
        is_io_metric: Bu metrik I/O ile mi ilgili (backup etkisi için)

    Kullanım:
    ---------
    ```python
    from sar_generator.config import PatternConfig

    pattern_config = PatternConfig(peak_hour=14, night_reduction_factor=0.4)
    diurnal = DiurnalPattern.from_config(pattern_config)

    # Öğlen saatinde CPU yük faktörü
    effect = diurnal.calculate(
        timestamp=datetime(2024, 1, 1, 12, 0),
        base_value=40.0
    )
    # effect ≈ +8.0 (base_value'nun %20'si kadar artış)
    ```
    """

    def __init__(
            self,
            business_hours_start: int = 9,
            business_hours_end: int = 18,
            peak_hour: int = 14,
            night_reduction: float = 0.4,
            backup_start: int = 2,
            backup_end: int = 4,
            backup_io_multiplier: float = 3.0,
            is_io_metric: bool = False
    ):
        self.business_hours_start = business_hours_start
        self.business_hours_end = business_hours_end
        self.peak_hour = peak_hour
        self.night_reduction = night_reduction
        self.backup_start = backup_start
        self.backup_end = backup_end
        self.backup_io_multiplier = backup_io_multiplier
        self.is_io_metric = is_io_metric

        # Saat bazlı yük profili oluştur (smooth geçişlerle)
        self._hourly_profile = self._build_hourly_profile()

    @classmethod
    def from_config(cls, pattern_config, is_io_metric: bool = False) -> "DiurnalPattern":
        """
        PatternConfig'ten DiurnalPattern oluşturur.

        Args:
            pattern_config: PatternConfig instance
            is_io_metric: Bu metrik I/O ile mi ilgili

        Returns:
            Yapılandırılmış DiurnalPattern instance
        """
        return cls(
            business_hours_start=pattern_config.business_hours_start,
            business_hours_end=pattern_config.business_hours_end,
            peak_hour=pattern_config.peak_hour,
            night_reduction=pattern_config.night_reduction_factor,
            backup_start=pattern_config.backup_window_start,
            backup_end=pattern_config.backup_window_end,
            backup_io_multiplier=pattern_config.backup_io_multiplier,
            is_io_metric=is_io_metric
        )

    def _build_hourly_profile(self) -> np.ndarray:
        """
        24 saatlik yük profilini oluşturur.

        Her saat için 0.0-1.0 arasında bir yük faktörü hesaplar.
        Sonuç, base_value'ya oranla ne kadar sapma olacağını belirler.

        Profil yapısı:
        - Gece saatleri (00-06): night_reduction seviyesinde
        - Ramp-up (06 → business_start): Kademeli artış
        - İş saatleri: Yüksek yük, peak_hour'da maksimum
        - Ramp-down (business_end → 22): Kademeli azalma
        - Geç akşam (22-24): night_reduction'a doğru azalma

        Returns:
            24 elemanlı numpy array (her saat için yük faktörü)
        """
        profile = np.zeros(24)

        for hour in range(24):
            if self.backup_start <= hour < self.backup_end and self.is_io_metric:
                # Backup penceresi — I/O metrikleri için yüksek yük
                profile[hour] = self.backup_io_multiplier - 1.0  # -1 çünkü base'e ekleniyor
            elif hour < 6:
                # Gece quiet period
                profile[hour] = -(1.0 - self.night_reduction)
            elif hour < self.business_hours_start:
                # Sabah ramp-up: gece seviyesinden iş saatlerine sigmoid geçiş
                progress = (hour - 6) / (self.business_hours_start - 6)
                smoothed = self._sigmoid(progress)
                night_level = -(1.0 - self.night_reduction)
                profile[hour] = night_level + smoothed * abs(night_level)
            elif hour <= self.business_hours_end:
                # İş saatleri — peak hour'a mesafeye göre yük
                distance_to_peak = abs(hour - self.peak_hour)
                max_distance = max(
                    self.peak_hour - self.business_hours_start,
                    self.business_hours_end - self.peak_hour
                )
                # Peak'te 1.0, kenarlarda 0.5 — parabolik profil
                if max_distance > 0:
                    normalized_distance = distance_to_peak / max_distance
                    profile[hour] = 0.5 * (1.0 - normalized_distance ** 1.5)
                else:
                    profile[hour] = 0.5
            elif hour < 22:
                # Akşam ramp-down
                progress = (hour - self.business_hours_end) / (22 - self.business_hours_end)
                smoothed = self._sigmoid(progress)
                profile[hour] = 0.3 * (1.0 - smoothed)
            else:
                # Geç akşam — gece seviyesine doğru
                progress = (hour - 22) / 2.0
                smoothed = self._sigmoid(progress)
                night_level = -(1.0 - self.night_reduction)
                profile[hour] = night_level * smoothed

        return profile

    def _sigmoid(self, x: float, steepness: float = 6.0) -> float:
        """
        Sigmoid fonksiyonu — yumuşak geçişler için.

        0-1 arasındaki input'u yine 0-1 arasında, ama S-şeklinde
        bir eğriyle dönüştürür. Bu sayede ramp-up ve ramp-down
        doğal görünür (ani sıçrama yerine kademeli artış).

        Args:
            x: 0.0-1.0 arasında input
            steepness: Eğrinin dikliği (yüksek = daha keskin geçiş)

        Returns:
            0.0-1.0 arasında sigmoid çıktısı
        """
        return 1.0 / (1.0 + np.exp(-steepness * (x - 0.5)))

    def calculate(self, timestamp: datetime, base_value: float) -> float:
        """
        Belirli bir zaman noktası için diurnal pattern etkisini hesaplar.

        Saat bazlı profili kullanır ve dakika bilgisine göre
        iki komşu saat arasında lineer interpolation yapar.
        Bu sayede saat başı geçişlerinde keskin sıçramalar oluşmaz.

        Args:
            timestamp: Zaman noktası
            base_value: Metriğin temel değeri

        Returns:
            Pattern etkisi (base_value'ya eklenecek offset)
            Pozitif = artış, negatif = azalma
        """
        hour = timestamp.hour
        minute = timestamp.minute

        # İki komşu saat arasında lineer interpolation
        current_factor = self._hourly_profile[hour]
        next_hour = (hour + 1) % 24
        next_factor = self._hourly_profile[next_hour]

        # Dakikaya göre interpolate et
        t = minute / 60.0
        interpolated_factor = current_factor * (1.0 - t) + next_factor * t

        # Base value ile çarparak gerçek etkiyi hesapla
        # Faktör ±0.6 civarında olabilir, bu da base_value'nun ±%60'ı demek
        effect = base_value * interpolated_factor * 0.4

        return effect

    def get_hourly_profile(self) -> np.ndarray:
        """
        24 saatlik yük profilini döndürür (debug/görselleştirme için).

        Returns:
            24 elemanlı numpy array
        """
        return self._hourly_profile.copy()

    def __repr__(self) -> str:
        return (
            f"DiurnalPattern(business={self.business_hours_start}-"
            f"{self.business_hours_end}, peak={self.peak_hour}, "
            f"night_red={self.night_reduction:.1f}, "
            f"io={self.is_io_metric})"
        )