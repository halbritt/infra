from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HA_CONFIG = (
    ROOT
    / "devices/home-assistant-fernside/config/home-assistant-core/configuration.yaml"
)
VM_CONFIG = ROOT / "hosts/proximal/config/observability/victoriametrics-homeassistant"
DASHBOARDS = ROOT / "hosts/proximal/config/observability/grafana/dashboards"


class HomeAssistantVictoriaMetricsTests(unittest.TestCase):
    def test_entity_allowlists_match_all_victoriametrics_consumers(self) -> None:
        ha_entities = set(
            re.findall(r"^\s+- sensor\.([a-z0-9_]+)$", HA_CONFIG.read_text(), re.M)
        )

        dashboard_entities: set[str] = set()
        for name in (
            "plant-moisture-victoriametrics.json",
            "indoor-environment-victoriametrics.json",
        ):
            dashboard = json.loads((DASHBOARDS / name).read_text())
            expressions = re.findall(
                r'entity_id=\\?"([a-z0-9_]+)', json.dumps(dashboard)
            )
            dashboard_entities.update(expressions)

        relabel = (VM_CONFIG / "relabel.yml").read_text()
        match = re.search(r'entity_id=~"\^\(([^)]+)\)\$"', relabel)
        self.assertIsNotNone(match, "relabel entity allowlist is missing")
        relabel_entities = set(match.group(1).split("|"))

        self.assertEqual(len(ha_entities), 34)
        self.assertEqual(dashboard_entities, ha_entities)
        self.assertEqual(relabel_entities, ha_entities)

    def test_victoriametrics_dashboards_use_only_the_query_datasource(self) -> None:
        for name in (
            "plant-moisture-victoriametrics.json",
            "indoor-environment-victoriametrics.json",
        ):
            dashboard = json.loads((DASHBOARDS / name).read_text())
            datasources = {
                match["datasource"]["uid"]
                for match in self._objects(dashboard)
                if isinstance(match.get("datasource"), dict)
                and "uid" in match["datasource"]
            }
            self.assertEqual(datasources, {"victoriametrics-ha"}, name)

    @classmethod
    def _objects(cls, value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from cls._objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._objects(child)


if __name__ == "__main__":
    unittest.main()
