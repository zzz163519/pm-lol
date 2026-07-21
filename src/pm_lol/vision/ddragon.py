from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


DDRAGON_BASE_URL = "https://ddragon.leagueoflegends.com/cdn"


@dataclass(frozen=True, slots=True)
class ChampionAsset:
    champion_id: str
    numeric_key: str
    name: str
    image_filename: str
    path: Path


class DDragonChampionStore:
    """Versioned local cache for Riot champion icons; assets are never committed."""

    def __init__(
        self,
        *,
        version: str,
        cache_root: Path,
        locale: str = "en_US",
        session: requests.Session | None = None,
        timeout_sec: float = 20.0,
    ) -> None:
        self.version = version
        self.locale = locale
        self.cache_dir = cache_root / version
        self.session = session or requests.Session()
        self.timeout_sec = timeout_sec

    @property
    def metadata_path(self) -> Path:
        return self.cache_dir / "champion.json"

    @property
    def image_dir(self) -> Path:
        return self.cache_dir / "img" / "champion"

    def sync(self) -> list[ChampionAsset]:
        self.image_dir.mkdir(parents=True, exist_ok=True)
        metadata = self._load_or_download_json(
            self.metadata_path,
            f"{DDRAGON_BASE_URL}/{self.version}/data/{self.locale}/champion.json",
        )
        assets: list[ChampionAsset] = []
        for champion_id, item in sorted(metadata["data"].items()):
            image_filename = str(item["image"]["full"])
            path = self.image_dir / image_filename
            if not path.is_file() or path.stat().st_size == 0:
                self._download_file(path, f"{DDRAGON_BASE_URL}/{self.version}/img/champion/{image_filename}")
            assets.append(
                ChampionAsset(
                    champion_id=champion_id,
                    numeric_key=str(item["key"]),
                    name=str(item["name"]),
                    image_filename=image_filename,
                    path=path,
                )
            )
        return assets

    def load(self) -> list[ChampionAsset]:
        if not self.metadata_path.is_file():
            raise FileNotFoundError(f"Data Dragon cache is missing: {self.metadata_path}")
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        assets: list[ChampionAsset] = []
        for champion_id, item in sorted(metadata["data"].items()):
            image_filename = str(item["image"]["full"])
            path = self.image_dir / image_filename
            if not path.is_file():
                raise FileNotFoundError(f"champion template is missing: {path}")
            assets.append(ChampionAsset(champion_id, str(item["key"]), str(item["name"]), image_filename, path))
        return assets

    def _load_or_download_json(self, path: Path, url: str) -> dict[str, Any]:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        response = self.session.get(url, timeout=self.timeout_sec)
        response.raise_for_status()
        payload = response.json()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def _download_file(self, path: Path, url: str) -> None:
        response = self.session.get(url, timeout=self.timeout_sec)
        response.raise_for_status()
        content = response.content
        if not content:
            raise ValueError(f"empty Data Dragon asset response: {url}")
        path.write_bytes(content)
