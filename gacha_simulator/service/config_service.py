import json
from pathlib import Path
from typing import Dict, Any, List


class ConfigService:
    def __init__(self, config_dir: str = 'data/config'):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def save_config(self, name: str, config: Dict[str, Any]) -> None:
        path = self.config_dir / f'{name}.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def load_config(self, name: str) -> Dict[str, Any]:
        path = self.config_dir / f'{name}.json'
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def list_configs(self) -> List[str]:
        return [p.stem for p in self.config_dir.glob('*.json')]
