import json
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class MoveCandidate:
    san: str
    confidence: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def save_json(data: Any, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class StableFrame:
    index: int
    path: str
    warped_path: str
    occupancy: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "path": self.path,
            "warped_path": self.warped_path,
            "occupancy": self.occupancy,
        }
