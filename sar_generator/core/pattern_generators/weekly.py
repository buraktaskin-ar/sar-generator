"""
Weekly (Haftalık) Pattern Generator
=====================================

Bu modül, 7 günlük döngüde tekrar eden zamansal desenleri üretir.
Telco Cloud ortamlarında gözlemlenen tipik haftalık pattern'ler:

1. Hafta İçi (Pazartesi-Cuma): Tam yük, iş saatleri pattern'i aktif
2. Hafta Sonu (Cumartesi-Pazar): Azaltılmış yük, daha stabil
3. Pazartesi Sabah Spike: Birikmiş işlerin tetiklenmesi, VM restart'ları
4. Cuma Akşam Azalma: İş saatleri sonrası erken düşüş
5. Pazar Gece: Haftalık bakım penceresi

Telco Cloud Özel Durumlar:
---------------------------
- Bazı Telco Cloud servisleri 7/24 çalışır (ses, data), bu yüzden
  hafta sonu azalması diğer sektörlere göre daha azdır
- Backup ve maintenance job'ları genellikle hafta sonuna planlanır
- Traffic pattern'leri abone davranışına bağlıdır
"""

from datetime import datetime
from typing import Optional
import numpy as np


class WeeklyPattern:
    """
    Haftalık (7 günlük) döngü deseni üretici.

    Her haftanın günü için bir yük çarpanı hesaplar.
    Hafta içi tam yük, hafta sonu azaltılmış yük uygulanır.

    Attributes:
        weekend_reduction: Hafta sonu yük azalma faktörü (0.0-1.0)
        monday_spike_factor: Pazartesi sabah spike çarpanı
        friday_early_reduction: Cuma erken azalma faktörü
        maintenance_day: Bakım günü (0=Pzt, 6=Paz, None=yok)
        maintenance_hour_start: Bakım başlangıç saati
        maintenance_io_boost: Bakım sırasında I/O artışı
        is_io_metric: I/O ile ilgili metrik mi

    Kullanım:
    ---------
    ```python
    weekly = WeeklyPattern(weekend_reduction=0.6)

    # Cumartesi günü yük faktörü
    effect = weekly.calculate(
        timestamp=datetime(2024, 1, 6, 12, 0),  # Cumartesi
        base_value=40.0
    )
    # effect ≈ -8.0 (%20 azalma)
    ```
    """

    def __init__(
            self,
            weekend_reduction: float = 0.6,
            monday_spike_factor: float = 1.15,
            friday_early_reduction: float = 0.9,
            maintenance_day: Optional[int] = 6,  # Pazar
            maintenance_hour_start: int = 2,
            maintenance_io_boost: float = 2.0,
            is_io_metric: bool = False
    ):
        self.weekend_reduction = weekend_reduction
        self.monday_spike_factor = monday_spike_factor
        self.friday_early_reduction = friday_early_reduction
        self.maintenance_day = maintenance_day
        self.maintenance_hour_start = maintenance_hour_start
        self.maintenance_io_boost = maintenance_io_boost
        self.is_io_metric = is_io_metric

        # Gün bazlı yük profili
        self._daily_profile = self._build_daily_profile()

    @classmethod
    def from_config(cls, pattern_config, is_io_metric: bool = False) -> "WeeklyPattern":
        """
        PatternConfig'ten WeeklyPattern oluşturur.

        Args:
            pattern_config: PatternConfig instance
            is_io_metric: Bu metrik I/O ile mi ilgili

        Returns:
            Yapılandırılmış WeeklyPattern instance
        """
        return cls(
            weekend_reduction=pattern_config.weekend_reduction_factor,
            is_io_metric=is_io_metric
        )

    def _build_daily_profile(self) -> np.ndarray:
        """
        7 günlük yük profilini oluşturur.

        Günler: 0=Pazartesi, 1=Salı, ..., 4=Cuma, 5=Cumartesi, 6=Pazar

        Returns:
            7 elemanlı numpy array (her gün için yük çarpanı)
        """
        profile = np.ones(7)

        # Hafta içi günler — küçük varyasyonlarla
        profile[0] = self.monday_spike_factor     # Pazartesi: spike
        profile[1] = 1.0                          # Salı: normal
        profile[2] = 1.0                          # Çarşamba: normal
        profile[3] = 0.98                         # Perşembe: hafif azalma
        profile[4] = self.friday_early_reduction  # Cuma: erken azalma

        # Hafta sonu — azaltılmış yük
        profile[5] = self.weekend_reduction        # Cumartesi
        profile[6] = self.weekend_reduction * 0.95 # Pazar: biraz daha az

        return profile

    def calculate(self, timestamp: datetime, base_value: float) -> float:
        """
        Belirli bir zaman noktası için haftalık pattern etkisini hesaplar.

        Günün yük çarpanını kullanır. Hafta sonu geçişlerinde
        (Cuma akşam → Cumartesi, Pazar gece → Pazartesi)
        smooth transition sağlanır.

        Args:
            timestamp: Zaman noktası
            base_value: Metriğin temel değeri

        Returns:
            Pattern etkisi (base_value'ya eklenecek offset)
        """
        weekday = timestamp.weekday()  # 0=Pzt, 6=Paz
        hour = timestamp.hour

        # Temel günlük faktörü al
        day_factor = self._daily_profile[weekday]

        # Gün geçişlerinde smooth transition
        # Örnek: Cuma 18:00 sonrası kademeli olarak Cumartesi seviyesine geçiş
        next_day = (weekday + 1) % 7
        next_day_factor = self._daily_profile[next_day]

        if hour >= 20:
            # Gece yarısına yaklaşırken sonraki güne smooth geçiş
            transition_progress = (hour - 20) / 4.0  # 20:00-24:00 arası
            day_factor = day_factor * (1 - transition_progress) + \
                         next_day_factor * transition_progress

        # Pazartesi sabah spike — sadece sabah saatlerinde aktif
        if weekday == 0 and 8 <= hour <= 11:
            spike_progress = (hour - 8) / 3.0
            # Spike giderek azalır (sabah en yüksek, öğlene doğru normal)
            spike_factor = 1.0 + (self.monday_spike_factor - 1.0) * (1.0 - spike_progress)
            day_factor *= spike_factor

        # Maintenance penceresi — I/O metrikleri için
        if (self.is_io_metric and
                self.maintenance_day is not None and
                weekday == self.maintenance_day and
                self.maintenance_hour_start <= hour < self.maintenance_hour_start + 4):
            day_factor *= self.maintenance_io_boost

        # Base_value'ya göre etkiyi hesapla
        # day_factor 1.0 ise etki 0 (değişiklik yok)
        # day_factor 0.6 ise etki negatif (%40 azalma)
        # day_factor 1.15 ise etki pozitif (%15 artış)
        effect = base_value * (day_factor - 1.0) * 0.3

        return effect

    def get_daily_profile(self) -> np.ndarray:
        """
        7 günlük yük profilini döndürür (debug/görselleştirme için).

        Returns:
            7 elemanlı numpy array
        """
        return self._daily_profile.copy()

    def __repr__(self) -> str:
        return (
            f"WeeklyPattern(weekend_red={self.weekend_reduction:.1f}, "
            f"monday_spike={self.monday_spike_factor:.2f}, "
            f"maint_day={self.maintenance_day})"
        )