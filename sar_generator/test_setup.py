import numpy as np
import pandas as pd
import scipy
import yaml
import pydantic
import click

print("=" * 50)
print("KÜTÜPHANE KONTROL TESTİ")
print("=" * 50)

print("\nNumPy version:", np.__version__)
print("Pandas version:", pd.__version__)
print("SciPy version:", scipy.__version__)
print("PyYAML yüklü: EVET")
print("Pydantic yüklü: EVET")
print("Click yüklü: EVET")

print("\n" + "=" * 50)
print("Tüm kütüphaneler başarıyla yüklendi!")
print("=" * 50)

# Basit bir tests
print("\nBASİT VERİ OLUŞTURMA TESTİ:")
print("-" * 50)

dates = pd.date_range(start='2024-01-01', end='2024-01-02', freq='5min')
cpu_usage = np.random.uniform(10, 80, len(dates))

print(f"Oluşturulan timestamp sayısı: {len(dates)}")
print(f"CPU kullanım aralığı: {cpu_usage.min():.2f}% - {cpu_usage.max():.2f}%")
print(f"Ortalama CPU kullanımı: {cpu_usage.mean():.2f}%")

print("\n✓ Test başarılı! Projeye başlamaya hazırsın.")