import json
import unittest
from unittest import mock

import plant_praxis_bridge as bridge


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class VictoriaMetricsLastTest(unittest.TestCase):
    @mock.patch.dict(bridge.os.environ, {
        "VICTORIAMETRICS_URL": "http://metrics.example:8427",
        "VICTORIAMETRICS_USER": "reader",
        "VICTORIAMETRICS_PASSWORD": "secret",
    }, clear=False)
    @mock.patch.object(bridge.time, "time", return_value=1_000)
    @mock.patch.object(bridge.urllib.request, "urlopen")
    def test_returns_value_and_age_from_real_sample_timestamp(self, urlopen, _time):
        urlopen.side_effect = [
            JsonResponse({"status": "success", "data": {"result": [
                {"metric": {}, "value": [1_000, "41.5"]},
            ]}}),
            JsonResponse({"status": "success", "data": {"result": [
                {"metric": {}, "value": [1_000, "877"]},
            ]}}),
        ]

        self.assertEqual(
            bridge.victoriametrics_last("dracaena_lisa_moisture_soil_moisture"),
            (41.5, 123.0),
        )
        self.assertEqual(urlopen.call_count, 2)
        for call in urlopen.call_args_list:
            request = call.args[0]
            self.assertEqual(request.full_url.split("?", 1)[0],
                             "http://metrics.example:8427/api/v1/query")
            self.assertTrue(request.get_header("Authorization").startswith("Basic "))

    @mock.patch.dict(bridge.os.environ, {
        "VICTORIAMETRICS_URL": "http://metrics.example:8427",
        "VICTORIAMETRICS_USER": "reader",
        "VICTORIAMETRICS_PASSWORD": "secret",
    }, clear=False)
    @mock.patch.object(bridge.urllib.request, "urlopen")
    def test_returns_none_only_when_the_value_series_is_absent(self, urlopen):
        urlopen.return_value = JsonResponse({
            "status": "success", "data": {"result": []},
        })

        self.assertIsNone(bridge.victoriametrics_last("missing_sensor"))
        urlopen.assert_called_once()


class MetricsBackendTest(unittest.TestCase):
    @mock.patch.dict(bridge.os.environ, {"METRICS_BACKEND": "victoriametrics"},
                     clear=False)
    @mock.patch.object(bridge, "victoriametrics_last", return_value=(44.0, 30.0))
    def test_dispatches_to_victoriametrics(self, victoria_last):
        self.assertEqual(bridge.metrics_last("plant_sensor"), (44.0, 30.0))
        victoria_last.assert_called_once_with("plant_sensor")

    @mock.patch.dict(bridge.os.environ, {}, clear=True)
    @mock.patch.object(bridge, "influx_last")
    def test_missing_backend_fails_closed(self, influx_last):
        with self.assertRaisesRegex(KeyError, "METRICS_BACKEND"):
            bridge.metrics_last("plant_sensor")
        influx_last.assert_not_called()


if __name__ == "__main__":
    unittest.main()
