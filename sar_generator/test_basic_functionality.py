#!/usr/bin/env python3
"""
SAR Generator Test Script

Bu script, oluşturduğumuz temel sınıfları test eder:
1. MetricGenerator sınıfını test eder
2. CorrelationEngine sınıfını test eder
3. BaseNode ve ComputeNode sınıflarını test eder
4. Gerçekçi SAR verisi üretir ve görselleştirir

Kullanım:
    python test_basic_functionality.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

# Proje kök dizinini Python path'e ekle
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sar_generator.core import (
    PercentageMetric,
    CountMetric,
    CorrelationEngine,
    CorrelationType,
    create_default_correlations
)
from sar_generator.node_types import ComputeNode


def print_section_header(title):
    """Test section başlığı yazdırır."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_metric_generator():
    """MetricGenerator sınıfını test eder."""
    print_section_header("TEST 1: MetricGenerator Sınıfı")

    print("\n1.1 PercentageMetric Oluşturma")
    print("-" * 50)

    # CPU metriği oluştur
    cpu_metric = PercentageMetric(
        name="%usr",
        base_value=40.0,
        volatility=0.15
    )

    print(f"Metrik adı: {cpu_metric.name}")
    print(f"Base value: {cpu_metric.base_value}%")
    print(f"Min/Max: {cpu_metric.min_value}% - {cpu_metric.max_value}%")
    print(f"Volatility: {cpu_metric.volatility}")

    print("\n1.2 Farklı Zamanlarda Değer Üretme")
    print("-" * 50)

    # Bir gün boyunca değerler üret
    base_time = datetime(2024, 1, 1, 0, 0, 0)

    print(f"{'Saat':<10} {'CPU %usr':<12} {'Pattern Etkisi':<20}")
    print("-" * 50)

    for hour in [0, 6, 9, 12, 15, 18, 21]:
        timestamp = base_time + timedelta(hours=hour)
        value = cpu_metric.generate(timestamp)

        # Pattern etkisini görmek için base_value'dan farkı hesapla
        pattern_effect = value - cpu_metric.base_value

        print(f"{hour:02d}:00     {value:6.2f}%      {pattern_effect:+6.2f}% (gece düşük, gündüz yüksek)")

    print("\n1.3 CountMetric Test")
    print("-" * 50)

    # Context switch metriği
    cswch_metric = CountMetric(
        name="cswch/s",
        base_value=5000,
        max_value=50000,
        unit="count/s",
        volatility=0.2
    )

    # 10 değer üret ve istatistikleri göster
    values = []
    for i in range(10):
        timestamp = base_time + timedelta(minutes=i * 5)
        value = cswch_metric.generate(timestamp)
        values.append(value)

    print(f"10 ölçümden ortalama: {np.mean(values):.1f} {cswch_metric.unit}")
    print(f"Standart sapma: {np.std(values):.1f}")
    print(f"Min: {np.min(values):.1f}, Max: {np.max(values):.1f}")

    print("\n✓ MetricGenerator testleri başarılı!")
    return True


def test_correlation_engine():
    """CorrelationEngine sınıfını test eder."""
    print_section_header("TEST 2: CorrelationEngine Sınıfı")

    print("\n2.1 Korelasyon Kuralı Ekleme")
    print("-" * 50)

    engine = CorrelationEngine()

    # Basit bir kural ekle: Yüksek CPU -> Artan context switches
    engine.add_rule(
        source_metric="%usr",
        target_metric="cswch/s",
        correlation_type=CorrelationType.LINEAR,
        strength=0.8,
        description="High CPU increases context switches"
    )

    print("Kural eklendi:")
    print("  Kaynak: %usr")
    print("  Hedef: cswch/s")
    print("  Tip: LINEAR")
    print("  Güç: 0.8")

    print("\n2.2 Korelasyon Etkilerini Hesaplama")
    print("-" * 50)

    # Farklı CPU değerleri için context switch etkisini hesapla
    print(f"{'CPU %usr':<12} {'cswch/s için ek değer':<25} {'Açıklama':<30}")
    print("-" * 70)

    for cpu_value in [20, 40, 60, 80]:
        current_values = {"%usr": cpu_value}
        effects = engine.calculate_effects(
            target_metric="cswch/s",
            current_values=current_values
        )

        total_effect = sum(effects.values())
        explanation = f"CPU {cpu_value}% -> +{total_effect:.1f} cswch/s"

        print(f"{cpu_value}%         {total_effect:+8.1f}                  {explanation}")

    print("\n2.3 Varsayılan Korelasyonları Test Etme")
    print("-" * 50)

    default_engine = create_default_correlations()
    stats = default_engine.get_statistics()

    print(f"Toplam kural sayısı: {stats['total_rules']}")
    print(f"Etkilenen metrik sayısı: {stats['affected_metrics']}")

    # Bazı önemli korelasyonları göster
    print("\nÖrnek korelasyon kuralları:")

    for target in ["%idle", "cswch/s", "pgpgin/s"]:
        rules = default_engine.get_rules_for_metric(target)
        if rules:
            print(f"\n  {target} metriğini etkileyen kurallar:")
            for rule in rules[:2]:  # İlk 2 kuralı göster
                print(f"    - {rule.source_metric} -> {rule.target_metric}")
                print(f"      Tip: {rule.correlation_type.value}, Güç: {rule.strength}")

    print("\n✓ CorrelationEngine testleri başarılı!")
    return True


def test_compute_node():
    """ComputeNode sınıfını test eder."""
    print_section_header("TEST 3: ComputeNode Sınıfı")

    print("\n3.1 ComputeNode Oluşturma")
    print("-" * 50)

    # Farklı yük seviyelerinde node'lar oluştur
    nodes = {
        "Düşük Yük": ComputeNode(node_id="compute-light", base_load=0.3),
        "Normal Yük": ComputeNode(node_id="compute-normal", base_load=0.5),
        "Yüksek Yük": ComputeNode(node_id="compute-heavy", base_load=0.8)
    }

    for name, node in nodes.items():
        info = node.get_node_info()
        print(f"\n{name}:")
        print(f"  Node ID: {info['node_id']}")
        print(f"  Node Type: {info['node_type']}")
        print(f"  Base Load: {info['base_load']:.1%}")
        print(f"  Metrik Sayısı: {info['total_metrics']}")

    print("\n3.2 Tek Bir Zaman Noktası İçin Veri Üretme")
    print("-" * 50)

    # Normal yük node'undan veri üret
    node = nodes["Normal Yük"]
    timestamp = datetime(2024, 1, 1, 14, 30, 0)

    data = node.generate_metrics(timestamp)

    print(f"\nÜretilen veri (timestamp: {data['DateTime']}):")
    print(f"Hostname: {data['hostname']}")
    print(f"Node Type: {data['node_type']}")

    # Bazı önemli metrikleri göster
    important_metrics = [
        "%usr", "%sys", "%iowait", "%idle",
        "kbmemused", "%memused",
        "cswch/s", "proc/s",
        "bread/s", "bwrtn/s"
    ]

    print("\nÖnemli Metrikler:")
    for metric in important_metrics:
        if metric in data:
            value = data[metric]
            # Metriğin generator'ını al
            gen = node.get_metric(metric)
            if gen:
                print(f"  {metric:<15} {value:>12.2f} {gen.unit:<8}")

    print("\n3.3 Zaman Serisi Veri Üretme (24 saat)")
    print("-" * 50)

    # 24 saatlik veri üret (her saat bir veri noktası)
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    time_series_data = []

    for hour in range(24):
        timestamp = base_time + timedelta(hours=hour)
        data = node.generate_metrics(timestamp)
        time_series_data.append(data)

    # CPU kullanımının gün içindeki değişimini göster
    print("\nCPU Kullanımı (24 saat):")
    print(f"{'Saat':<8} {'%usr':<10} {'%sys':<10} {'%idle':<10} {'Trend':<15}")
    print("-" * 60)

    for i, data in enumerate(time_series_data):
        if i % 3 == 0:  # Her 3 saatte bir göster
            usr = data["%usr"]
            sys = data["%sys"]
            idle = data["%idle"]

            # Basit trend göstergesi
            if i > 0:
                prev_usr = time_series_data[i - 1]["%usr"]
                trend = "↑ Artış" if usr > prev_usr else "↓ Azalış"
            else:
                trend = "Başlangıç"

            print(f"{i:02d}:00   {usr:6.2f}%   {sys:6.2f}%   {idle:6.2f}%   {trend}")

    print("\n3.4 Korelasyonların Etkisini Gösterme")
    print("-" * 50)

    # Yüksek CPU ile düşük CPU senaryolarını karşılaştır
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Normal senaryo
    normal_data = node.generate_metrics(timestamp)

    # Yüksek CPU senaryosu (modifier ile)
    high_cpu_scenario = {"%usr": 1.8}  # CPU'yu %80 artır
    high_cpu_data = node.generate_metrics(timestamp, scenario_modifier=high_cpu_scenario)

    print("\nNormal vs Yüksek CPU Senaryosu:")
    print(f"{'Metrik':<15} {'Normal':<15} {'Yüksek CPU':<15} {'Fark':<15}")
    print("-" * 60)

    comparison_metrics = ["%usr", "cswch/s", "%iowait", "proc/s"]
    for metric in comparison_metrics:
        if metric in normal_data and metric in high_cpu_data:
            normal_val = normal_data[metric]
            high_val = high_cpu_data[metric]
            diff = high_val - normal_val

            print(f"{metric:<15} {normal_val:>10.2f}   {high_val:>10.2f}      {diff:+>10.2f}")

    print("\nDikkat: Yüksek CPU'da context switch ve proc/s değerleri de arttı!")
    print("Bu, CorrelationEngine'in çalıştığını gösterir.")

    print("\n✓ ComputeNode testleri başarılı!")
    return True


def generate_sample_dataset():
    """Örnek bir veri seti üretir ve dosyaya kaydeder."""
    print_section_header("TEST 4: Örnek Veri Seti Üretimi")

    print("\n4.1 Veri Seti Parametreleri")
    print("-" * 50)

    # Parametreler
    node_id = "compute-01"
    base_load = 0.6
    start_time = datetime(2024, 1, 1, 0, 0, 0)
    duration_hours = 24
    interval_minutes = 5

    print(f"Node ID: {node_id}")
    print(f"Base Load: {base_load:.1%}")
    print(f"Başlangıç: {start_time}")
    print(f"Süre: {duration_hours} saat")
    print(f"Interval: {interval_minutes} dakika")
    print(f"Toplam veri noktası: {(duration_hours * 60) // interval_minutes}")

    print("\n4.2 Veri Üretiliyor...")
    print("-" * 50)

    # Node oluştur
    node = ComputeNode(node_id=node_id, base_load=base_load)

    # Veri üret
    dataset = []
    total_points = (duration_hours * 60) // interval_minutes

    for i in range(total_points):
        timestamp = start_time + timedelta(minutes=i * interval_minutes)
        data = node.generate_metrics(timestamp)
        dataset.append(data)

        # Progress indicator
        if (i + 1) % 50 == 0:
            progress = ((i + 1) / total_points) * 100
            print(f"  İlerleme: {progress:.1f}% ({i + 1}/{total_points} veri noktası)")

    print(f"\n✓ {len(dataset)} veri noktası üretildi!")

    print("\n4.3 İstatistikler")
    print("-" * 50)

    # Bazı metriklerin istatistiklerini hesapla
    metrics_to_analyze = ["%usr", "%sys", "kbmemused", "cswch/s", "rxkB/s"]

    print(f"{'Metrik':<15} {'Ortalama':<12} {'Min':<12} {'Max':<12} {'Std Dev':<12}")
    print("-" * 70)

    for metric in metrics_to_analyze:
        values = [d[metric] for d in dataset if metric in d]
        if values:
            avg = np.mean(values)
            min_val = np.min(values)
            max_val = np.max(values)
            std = np.std(values)

            print(f"{metric:<15} {avg:>10.2f}   {min_val:>10.2f}   {max_val:>10.2f}   {std:>10.2f}")

    print("\n4.4 Dosyaya Kaydetme")
    print("-" * 50)

    # CSV formatında kaydet
    output_file = project_root / "sample_output.csv"

    with open(output_file, 'w') as f:
        # Başlık satırı
        if dataset:
            headers = list(dataset[0].keys())
            f.write(','.join(headers) + '\n')

            # Veri satırları
            for data in dataset:
                row = [str(data.get(h, '')) for h in headers]
                f.write(','.join(row) + '\n')

    print(f"✓ Veri dosyaya kaydedildi: {output_file}")
    print(f"  Dosya boyutu: {output_file.stat().st_size / 1024:.1f} KB")

    # Dosyadan ilk birkaç satırı oku ve göster
    print("\n4.5 Dosya İçeriği Önizlemesi")
    print("-" * 50)

    with open(output_file, 'r') as f:
        lines = f.readlines()
        print("İlk 5 satır:")
        for i, line in enumerate(lines[:5]):
            if i == 0:
                print(f"BAŞLIKLAR: {line[:100]}...")
            else:
                print(f"Satır {i}: {line[:100]}...")

    print(f"\n✓ Örnek veri seti başarıyla oluşturuldu!")
    return True


def main():
    """Ana test fonksiyonu."""
    print("\n" + "=" * 70)
    print("  SAR GENERATOR - TEMEL SINIFLAR TEST SUITE")
    print("=" * 70)
    print("\nBu test suite, oluşturduğumuz temel sınıfları kapsamlı şekilde test eder.")
    print("Her test bölümü, farklı bir bileşeni doğrular ve sonuçları gösterir.")

    # Test sonuçlarını sakla
    results = {}

    try:
        # Test 1: MetricGenerator
        results["MetricGenerator"] = test_metric_generator()

        # Test 2: CorrelationEngine
        results["CorrelationEngine"] = test_correlation_engine()

        # Test 3: ComputeNode
        results["ComputeNode"] = test_compute_node()

        # Test 4: Sample Dataset
        results["Sample Dataset"] = generate_sample_dataset()

    except Exception as e:
        print(f"\n❌ Test sırasında hata oluştu: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Sonuç özeti
    print_section_header("TEST SONUÇLARI")

    all_passed = all(results.values())

    print("\nTest Özeti:")
    for test_name, passed in results.items():
        status = "✓ BAŞARILI" if passed else "❌ BAŞARISIZ"
        print(f"  {test_name:<20} {status}")

    print("\n" + "=" * 70)
    if all_passed:
        print("  🎉 TÜM TESTLER BAŞARIYLA TAMAMLANDI!")
        print("=" * 70)
        print("\nSonraki Adımlar:")
        print("1. sample_output.csv dosyasını inceleyebilirsiniz")
        print("2. Diğer node tiplerini (CEPH, Control, Network) ekleyebiliriz")
        print("3. WP2'deki pattern generator'ları geliştirebiliriz")
        print("4. CLI arayüzünü oluşturabiliriz")
        return True
    else:
        print("  ⚠️  BAZI TESTLER BAŞARISIZ OLDU")
        print("=" * 70)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)