from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests

from .ddragon import ChampionAsset


CDRAGON_ROOT = "https://raw.communitydragon.org/{version}/plugins/rcp-be-lol-game-data/global/default"


class CDragonChampionSplashStore:
    """Versioned local cache for centered champion-select splash art."""

    asset_field = "splashPath"
    asset_dirname = "centered"
    asset_label = "splash"

    def __init__(
        self,
        *,
        version: str,
        cache_root: Path,
        session: requests.Session | None = None,
        timeout_sec: float = 30.0,
    ) -> None:
        self.version = version
        self.cache_dir = cache_root / version
        self.session = session or requests.Session()
        self.timeout_sec = timeout_sec

    @property
    def summary_path(self) -> Path:
        return self.cache_dir / "champion-summary.json"

    @property
    def image_dir(self) -> Path:
        return self.cache_dir / self.asset_dirname

    @property
    def metadata_dir(self) -> Path:
        return self.cache_dir / "champions"

    def sync(self) -> list[ChampionAsset]:
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        summary = self._summary()
        champions = [item for item in summary if int(item.get("id", -1)) >= 0]
        with ThreadPoolExecutor(max_workers=8) as pool:
            assets = list(pool.map(self._sync_one, champions))
        return sorted(assets, key=lambda asset: asset.champion_id)

    def load(self) -> list[ChampionAsset]:
        summary = self._summary(require_cached=True)
        assets = []
        for item in summary:
            numeric_id = int(item.get("id", -1))
            if numeric_id < 0:
                continue
            champion_id = str(item["alias"])
            path = self.image_dir / f"{champion_id}.jpg"
            if not path.is_file():
                raise FileNotFoundError(f"champion-select template is missing: {path}")
            assets.append(
                ChampionAsset(champion_id, str(numeric_id), str(item["name"]), path.name, path)
            )
        return assets

    def _sync_one(self, item: dict[str, Any]) -> ChampionAsset:
        numeric_id = int(item["id"])
        champion_id = str(item["alias"])
        metadata_path = self.metadata_dir / f"{numeric_id}.json"
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        else:
            url = f"{CDRAGON_ROOT.format(version=self.version)}/v1/champions/{numeric_id}.json"
            response = self.session.get(url, timeout=self.timeout_sec)
            response.raise_for_status()
            metadata = response.json()
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        asset_path = str(metadata["skins"][0][self.asset_field])
        prefix = "/lol-game-data/assets/"
        if not asset_path.lower().startswith(prefix):
            raise ValueError(
                f"unexpected CommunityDragon {self.asset_label} path: {asset_path}"
            )
        relative = asset_path[len(prefix) :].lower()
        url = f"{CDRAGON_ROOT.format(version=self.version)}/{relative}"
        filename = f"{champion_id}.jpg"
        path = self.image_dir / filename
        if not path.is_file() or path.stat().st_size == 0:
            response = self.session.get(url, timeout=self.timeout_sec)
            response.raise_for_status()
            if not response.content:
                raise ValueError(f"empty CommunityDragon asset response: {url}")
            path.write_bytes(response.content)
        return ChampionAsset(champion_id, str(numeric_id), str(item["name"]), filename, path)

    def _summary(self, *, require_cached: bool = False) -> list[dict[str, Any]]:
        if not self.summary_path.is_file():
            if require_cached:
                raise FileNotFoundError(f"CommunityDragon cache is missing: {self.summary_path}")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            url = f"{CDRAGON_ROOT.format(version=self.version)}/v1/champion-summary.json"
            response = self.session.get(url, timeout=self.timeout_sec)
            response.raise_for_status()
            self.summary_path.write_text(
                json.dumps(response.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        payload = json.loads(self.summary_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("CommunityDragon champion summary must be a list")
        return payload


class CDragonChampionTileStore(CDragonChampionSplashStore):
    """Versioned local cache for small draft ban tile art."""

    asset_field = "tilePath"
    asset_dirname = "tile"
    asset_label = "tile"
