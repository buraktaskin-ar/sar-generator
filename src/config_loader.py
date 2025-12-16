import yaml
from pathlib import Path
from typing import Dict, Any


class ConfigLoader:
    """YAML konfigürasyon dosyasını okur ve validate eder"""

    def __init__(self, config_path: str):
        """
        Args:
            config_path: YAML dosyasının yolu
        """
        self.config_path = Path(config_path)
        self.config_data = None

    def load(self) -> Dict[str, Any]:
        """Konfigürasyon dosyasını yükler"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config dosyası bulunamadı: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as file:
            self.config_data = yaml.safe_load(file)

        print(f"✓ Config dosyası yüklendi: {self.config_path}")
        return self.config_data

    def get_simulation_settings(self) -> Dict[str, Any]:
        """Simülasyon ayarlarını döndürür"""
        if self.config_data is None:
            raise ValueError("Önce load() metodunu çağırmalısınız")
        return self.config_data.get('simulation', {})

    def get_nodes(self) -> list:
        """Node listesini döndürür"""
        if self.config_data is None:
            raise ValueError("Önce load() metodunu çağırmalısınız")
        return self.config_data.get('nodes', [])

    def get_output_settings(self) -> Dict[str, Any]:
        """Çıktı ayarlarını döndürür"""
        if self.config_data is None:
            raise ValueError("Önce load() metodunu çağırmalısınız")
        return self.config_data.get('output', {})


# Test etmek için
if __name__ == "__main__":
    # Config dosyasının yolunu belirt
    config_path = "../config/default_config.yaml"

    # Config loader oluştur ve yükle
    loader = ConfigLoader(config_path)
    config = loader.load()

    # Ayarları yazdır
    print("\n--- Simülasyon Ayarları ---")
    sim_settings = loader.get_simulation_settings()
    print(f"Başlangıç: {sim_settings['start_time']}")
    print(f"Bitiş: {sim_settings['end_time']}")
    print(f"Interval: {sim_settings['interval_seconds']} saniye")

    print("\n--- Node'lar ---")
    nodes = loader.get_nodes()
    for node in nodes:
        print(f"- {node['type']}: {node['count']} adet, base load: {node['base_load']}")

    print("\n--- Çıktı Ayarları ---")
    output = loader.get_output_settings()
    print(f"Format: {output['format']}")
    print(f"Klasör: {output['directory']}")