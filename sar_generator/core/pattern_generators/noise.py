"""
Noise Generator - Gelişmiş Gürültü Modeli
==========================================

Bu modül, metriklere gerçekçi rastgele dalgalanmalar ekler.
Basit Gaussian noise yerine, birden fazla gürültü bileşenini birleştirir:

1. Gaussian Base Noise: Temel rastgele dalgalanma (her zaman)
2. Micro-Burst: Kısa süreli ani sıçramalar (nadir ama gerçekçi)
3. Brownian Drift: Yavaşça değişen offset (autocorrelated noise)

Neden Bu Kadar Detay?
---------------------
Gerçek sistem metriklerinde sadece rastgele noise yoktur. Bir CPU metriği
düz bir çizginin etrafında titremez — bazen kısa süreli spike'lar olur
(bir process anlık yük yaratır), bazen de genel seviye yavaşça kayar
(thermal throttling, background job'lar vb.).

Bu üç bileşen birleşince, üretilen veri gerçek SAR loglarına çok
daha yakın görünür. Bir veri bilimci veya operatör baktığında
"bu gerçek veri" diyebilmelidir.

Bileşenlerin Katkısı:
--------------------
- Gaussian: %70 (temel rastgelelik)
- Micro-burst: %15 (ani sıçramalar, nadir)
- Brownian drift: %15 (yavaş kayma)
"""

from typing import Optional
import numpy as np


class NoiseGenerator:
    """
    Çok katmanlı gürültü üretici.

    Üç farklı gürültü bileşenini birleştirerek gerçekçi
    metrik dalgalanmaları üretir.

    Attributes:
        burst_probability: Micro-burst olasılığı (0.0-1.0)
        burst_magnitude: Burst büyüklük çarpanı
        drift_momentum: Brownian drift momentum'u (0.0-1.0, yüksek=yavaş değişim)
        drift_strength: Drift'in base_value'ya oranı
        gaussian_weight: Gaussian noise ağırlığı
        burst_weight: Burst noise ağırlığı
        drift_weight: Drift noise ağırlığı

    Kullanım:
    ---------
    ```python
    noise = NoiseGenerator(burst_probability=0.05)

    # Tek bir noise değeri üret
    noise_value = noise.generate(base_value=40.0, volatility=0.15)
    # noise_value ≈ ±2.0 (genellikle), bazen ±10.0 (burst)
    ```
    """

    def __init__(
            self,
            burst_probability: float = 0.05,
            burst_magnitude: float = 3.0,
            drift_momentum: float = 0.95,
            drift_strength: float = 0.05,
            gaussian_weight: float = 0.70,
            burst_weight: float = 0.15,
            drift_weight: float = 0.15
    ):
        self.burst_probability = burst_probability
        self.burst_magnitude = burst_magnitude
        self.drift_momentum = drift_momentum
        self.drift_strength = drift_strength
        self.gaussian_weight = gaussian_weight
        self.burst_weight = burst_weight
        self.drift_weight = drift_weight

        # Brownian drift dahili durumu
        self._current_drift = 0.0

        # İstatistik sayaçları (debug için)
        self._total_calls = 0
        self._burst_count = 0

    @classmethod
    def from_quality_level(cls, quality: str) -> "NoiseGenerator":
        """
        Veri kalite seviyesine göre NoiseGenerator oluşturur.

        Args:
            quality: "low", "medium", "high"

        Returns:
            Kalite seviyesine uygun NoiseGenerator
        """
        configs = {
            "low": {
                "burst_probability": 0.10,
                "burst_magnitude": 4.0,
                "drift_momentum": 0.90,
                "drift_strength": 0.08,
            },
            "medium": {
                "burst_probability": 0.05,
                "burst_magnitude": 3.0,
                "drift_momentum": 0.95,
                "drift_strength": 0.05,
            },
            "high": {
                "burst_probability": 0.02,
                "burst_magnitude": 2.5,
                "drift_momentum": 0.97,
                "drift_strength": 0.03,
            },
        }

        config = configs.get(quality, configs["medium"])
        return cls(**config)

    def generate(self, base_value: float, volatility: float) -> float:
        """
        Tek bir noise değeri üretir.

        Üç bileşeni ağırlıklarına göre birleştirir:
        1. Gaussian base noise
        2. Micro-burst (olasılıkla)
        3. Brownian drift (momentum ile)

        Args:
            base_value: Metriğin temel değeri (noise büyüklüğünü ölçekler)
            volatility: Metriğin değişkenlik katsayısı (0.0-1.0)

        Returns:
            Toplam noise değeri (base_value'ya eklenecek)
        """
        self._total_calls += 1

        # Noise ölçeği — base_value ve volatility'ye bağlı
        scale = abs(base_value) * volatility * 0.1
        if scale < 0.001:
            scale = 0.001  # Minimum scale (base_value 0 olsa bile noise üret)

        # === Bileşen 1: Gaussian Base Noise ===
        # Standart normal dağılım — en temel dalgalanma
        gaussian_noise = np.random.normal(0, scale)

        # === Bileşen 2: Micro-Burst ===
        # Nadir ama belirgin sıçramalar
        # Gerçek sistemlerde kısa süreli process spike'ları, GC pauses vb. buna karşılık gelir
        burst_noise = 0.0
        if np.random.random() < self.burst_probability:
            # Burst gerçekleşti!
            self._burst_count += 1
            # Yön rastgele (pozitif veya negatif spike)
            burst_direction = np.random.choice([-1.0, 1.0], p=[0.3, 0.7])
            # Büyüklük — normal noise'un birkaç katı
            burst_noise = burst_direction * scale * self.burst_magnitude * \
                          np.random.exponential(1.0)

        # === Bileşen 3: Brownian Drift ===
        # Yavaşça değişen offset — momentum ile eski değere yapışır
        # Bu, metriğin "seviyesinin" yavaşça kaymasını simüle eder
        drift_innovation = np.random.normal(0, scale * self.drift_strength)
        self._current_drift = (
                self.drift_momentum * self._current_drift +
                (1.0 - self.drift_momentum) * drift_innovation
        )

        # === Bileşenleri Ağırlıklı Birleştir ===
        total_noise = (
                self.gaussian_weight * gaussian_noise +
                self.burst_weight * burst_noise +
                self.drift_weight * self._current_drift
        )

        return total_noise

    def reset(self):
        """
        Dahili durumu sıfırlar.

        Yeni bir simülasyon başlatırken çağrılmalıdır.
        Brownian drift sıfırlanır, istatistikler temizlenir.
        """
        self._current_drift = 0.0
        self._total_calls = 0
        self._burst_count = 0

    def get_statistics(self) -> dict:
        """
        Gürültü üretimi hakkında istatistik döndürür.

        Returns:
            İstatistik dictionary'si
        """
        burst_rate = (self._burst_count / self._total_calls * 100
                      if self._total_calls > 0 else 0)
        return {
            "total_calls": self._total_calls,
            "burst_count": self._burst_count,
            "burst_rate_percent": round(burst_rate, 2),
            "current_drift": round(self._current_drift, 4),
            "expected_burst_prob": self.burst_probability * 100
        }

    def __repr__(self) -> str:
        return (
            f"NoiseGenerator(burst_prob={self.burst_probability:.2f}, "
            f"burst_mag={self.burst_magnitude:.1f}, "
            f"drift_mom={self.drift_momentum:.2f})"
        )