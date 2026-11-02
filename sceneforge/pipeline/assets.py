from __future__ import annotations

from pathlib import Path

from sceneforge.schema.config import MinerConfig
from sceneforge.schema.rates import RateTable

DATA_DIR = Path(__file__).parents[2] / "data"
PROMPTS_DIR = DATA_DIR / "prompts"
CONFIG_PATH = DATA_DIR / "config.json"
PRICING_PATH = DATA_DIR / "pricing.json"
PLACEHOLDER_PATH = DATA_DIR / "placeholder.js"


def rate_table(path: Path) -> RateTable:
    return RateTable.model_validate_json(path.read_text(encoding="utf-8"))


def prompt_files(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(directory.rglob("*"))
        if path.suffix in (".md", ".json")
    }


def load_config(path: Path, prompts: Path, rates: RateTable) -> MinerConfig:
    return MinerConfig.load(path.read_text(encoding="utf-8"), prompt_files(prompts), rates)
