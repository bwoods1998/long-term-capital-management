"""Native checkpoint metadata through fabricated HTTP only; no sockets or keys."""
import copy
import io
import json
import unittest
from http.client import IncompleteRead
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from league import sailbox
from league.sailbox import SailboxClient, SailboxError, SailboxTransportError, Transport

BOX = "sb_9c8f1e2a-3b4d-4f5a-8c7e-1d2f3a4b5c6d"
APP = "app_0f6a2c31-8b4d-4e7a-9c15-2d8e6f4a1b03"
CP = "sbcp_1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
CP2 = "sbcp_2a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
NAME = "ltcm-source-trainval-export-20261005"
SECRET = "synthetic-checkpoint-auth-never-a-real-credential"


def checkpoint(cid=CP, **changes):
    return {"checkpoint_id": cid, "sailbox_id": BOX, "app_id": APP, "name": NAME,
            "checkpoint_generation": 918, "created_at": "2026-10-05T11:20:00Z",
            "expires_at": "2026-10-12T11:20:00Z", **changes}


def page(rows=(), limit=100, offset=0, has_more=False, **extra):
    return {"data": list(rows), "limit": limit, "offset": offset, "has_more": has_more, **extra}


class Response(io.BytesIO):
    def __init__(self, raw, headers=None, error=None):
        super().__init__(raw)
        self.headers = headers or {}
        self.error = error
        self.reads = []

    def read(self, size=-1):
        self.reads.append(size)
        if self.error is not None:
            raise self.error
        return super().read(size)


class FakeHTTP:
    def __init__(self, *answers):
        self.answers, self.calls, self.responses = list(answers), [], []

    def open(self, request, timeout):
        parsed = urlsplit(request.full_url)
        self.calls.append({"method": request.get_method(), "host": parsed.netloc,
            "path": parsed.path, "query": parse_qs(parsed.query, keep_blank_values=True),
            "body": request.data, "timeout": timeout})
        if not self.answers:
            raise AssertionError("unexpected additional native call")
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        if not isinstance(answer, Response):
            answer = Response(json.dumps(answer).encode())
        self.responses.append(answer)
        return answer


class CheckpointMetadataTests(unittest.TestCase):
    def client(self, *answers):
        http = FakeHTTP(*answers)
        client = SailboxClient(Transport(key_source=lambda: SECRET, opener=http))
        return client, http

    def test_documented_get_routes_are_allowed_but_no_delete_or_mutation(self):
        allowed = Transport(key_source=lambda: SECRET, opener=object()).allowed
        for path in ("/sailbox-checkpoints", "/sailbox-checkpoints/" + CP):
            self.assertTrue(allowed("GET", path))
            for method in ("POST", "PUT", "DELETE", "PATCH"):
                self.assertFalse(allowed(method, path))
        for path in ("/sailbox-checkpoints/", "/sailbox-checkpoints/../secrets",
                     "/sailbox-checkpoints/" + CP + "/files", "/sailbox-checkpoints/" + CP + "\n"):
            self.assertFalse(allowed("GET", path))

    def test_info_has_exact_native_get_shape_and_preserves_future_fields(self):
        row = checkpoint(status="future_checkpoint_status", native_future={"kept": True})
        client, http = self.client(row)
        self.assertEqual(client.checkpoint_info(CP, sailbox=BOX, app=APP, name=NAME), row)
        self.assertEqual(http.calls, [{"method": "GET", "host": sailbox.API_HOST,
            "path": "/v1/sailbox-checkpoints/" + CP, "query": {}, "body": None, "timeout": 60.0}])

    def test_null_name_and_expiry_are_documented_not_guessed_terminal(self):
        row = checkpoint(name=None, expires_at=None, status="not-a-known-enum")
        client, http = self.client(row)
        self.assertEqual(client.checkpoint_info(CP), row)
        self.assertEqual(len(http.calls), 1)

    def test_list_passes_and_revalidates_all_exact_filters(self):
        client, http = self.client(page([checkpoint()]))
        result = client.list_checkpoints(sailbox=BOX, app=APP, name=NAME)
        self.assertEqual(result["data"], [checkpoint()])
        self.assertFalse(result["has_more"]); self.assertIsNone(result["next_offset"])
        self.assertEqual(http.calls[0]["query"], {"sailbox_id": [BOX], "app": [APP], "name": [NAME], "limit": ["100"], "offset": ["0"]})
        self.assertEqual(http.calls[0]["method"], "GET"); self.assertIsNone(http.calls[0]["body"])

    def test_optional_filters_and_exact_empty_name_are_not_made_up(self):
        client, http = self.client(page([checkpoint(name="")]))
        result = client.list_checkpoints(name="")
        self.assertEqual(result["data"][0]["name"], "")
        self.assertEqual(http.calls[0]["query"], {"name": [""], "limit": ["100"], "offset": ["0"]})

    def test_bounded_multi_page_offsets_and_raw_page_fields_survive(self):
        client, http = self.client(page([checkpoint()], limit=1, offset=5, has_more=True, server_future="page1"),
            page([checkpoint(CP2)], limit=1, offset=6, server_future="page2"))
        result = client.list_checkpoints(sailbox=BOX, app=APP, name=NAME, limit=1, offset=5)
        self.assertEqual([r["checkpoint_id"] for r in result["data"]], [CP, CP2])
        self.assertEqual([c["query"]["offset"] for c in http.calls], [["5"], ["6"]])
        self.assertEqual([p["server_future"] for p in result["pages"]], ["page1", "page2"])
        self.assertFalse(result["has_more"])

    def test_page_cap_preserves_partial_has_more_instead_of_claiming_absence(self):
        client, http = self.client(page([checkpoint()], limit=1, has_more=True))
        result = client.list_checkpoints(limit=1, max_pages=1)
        self.assertEqual(result["data"], [checkpoint()])
        self.assertTrue(result["has_more"]); self.assertEqual(result["next_offset"], 1)
        self.assertEqual(len(http.calls), 1)

    def test_valid_empty_native_page_is_distinct_from_http404(self):
        client, http = self.client(page())
        result = client.list_checkpoints()
        self.assertEqual(result["data"], []); self.assertFalse(result["has_more"])
        self.assertEqual(len(http.calls), 1)

    def test_404_and_other_native_errors_propagate_without_fallback(self):
        for status in (400, 401, 402, 403, 404, 429, 500, 503):
            for info in (False, True):
                error = HTTPError("https://sailbox-api.sailresearch.com/v1/sailbox-checkpoints", status,
                                  "fabricated refusal", {}, io.BytesIO(b'{"error":{"message":"native route unknown","type":"not_found_error"}}'))
                client, http = self.client(error)
                with self.subTest(status=status, info=info), self.assertRaises(SailboxError) as caught:
                    client.checkpoint_info(CP) if info else client.list_checkpoints()
                self.assertEqual(caught.exception.status, status)
                self.assertEqual(len(http.calls), 1)
                self.assertEqual(http.calls[0]["method"], "GET")

    def test_legacy_checkpoints_keeps_record_join_and_one_box_get(self):
        client, http = self.client({"checkpoint_generation": 919, "last_checkpointed_at": "2026-10-05T11:20:00Z"})
        record = [{"checkpoint_id": CP, "name": NAME}]
        result = client.checkpoints(BOX, recorded=record)
        self.assertEqual(result, {"sailbox_id": BOX, "checkpoint_generation": 919,
                                 "last_checkpointed_at": "2026-10-05T11:20:00Z", "recorded": record})
        self.assertEqual([c["path"] for c in http.calls], ["/v1/sailboxes/" + BOX])

    def test_invalid_filter_or_id_refuses_before_transport_and_credentials(self):
        key = Mock(side_effect=AssertionError("credential requested"))
        client = SailboxClient(Transport(key_source=key, opener=object()))
        for kw in ({"sailbox": "../box"}, {"sailbox": BOX + "\n"}, {"app": "other"}, {"app": APP + "\n"},
                   {"name": "bad\n"}, {"name": "x" * 129}, {"name": 3}):
            with self.subTest(kw=kw), self.assertRaises(SailboxError): client.list_checkpoints(**kw)
            with self.subTest(kw=kw), self.assertRaises(SailboxError): client.checkpoint_info(CP, **kw)
        for cid in (None, "../checkpoint", CP + "\n", CP + "/files"):
            with self.subTest(cid=cid), self.assertRaises(SailboxError): client.checkpoint_info(cid)
        key.assert_not_called()

    def test_bad_pagination_bounds_refuse_before_transport(self):
        client, http = self.client()
        for field, bads in (("limit", (0, 101, True, 1.0)), ("offset", (-1, 100001, True)), ("max_pages", (0, 51, True))):
            for bad in bads:
                with self.subTest(field=field, bad=bad), self.assertRaises(SailboxError):
                    client.list_checkpoints(**{field: bad})
        self.assertEqual(http.calls, [])

    def test_wrong_info_identity_or_source_app_name_refuses(self):
        for changes in ({"checkpoint_id": CP2}, {"sailbox_id": "sb_00000000"}, {"app_id": "app_00000000"}, {"name": "near-name"}):
            client, http = self.client(checkpoint(**changes))
            with self.subTest(changes=changes), self.assertRaises(SailboxError):
                client.checkpoint_info(CP, sailbox=BOX, app=APP, name=NAME)
            self.assertEqual(len(http.calls), 1)

    def test_foreign_list_row_refuses_whole_inventory_not_silent_filter(self):
        for changes in ({"sailbox_id": "sb_00000000"}, {"app_id": "app_00000000"}, {"name": "near-name"}):
            client, http = self.client(page([checkpoint(), checkpoint(CP2, **changes)]))
            with self.subTest(changes=changes), self.assertRaises(SailboxError):
                client.list_checkpoints(sailbox=BOX, app=APP, name=NAME)
            self.assertEqual(len(http.calls), 1)

    def test_duplicate_row_within_and_across_pages_refuses_without_more_gets(self):
        client, http = self.client(page([checkpoint(), checkpoint()]))
        with self.assertRaisesRegex(SailboxError, "repeated"): client.list_checkpoints()
        self.assertEqual(len(http.calls), 1)
        client, http = self.client(page([checkpoint()], limit=1, has_more=True), page([checkpoint()], limit=1, offset=1, has_more=True))
        with self.assertRaisesRegex(SailboxError, "repeated"): client.list_checkpoints(limit=1)
        self.assertEqual(len(http.calls), 2)

    def test_malformed_page_never_means_empty_success(self):
        for bad in (None, {}, {"data": []}, page([], has_more=True), page([checkpoint()], offset=1), page([checkpoint()], limit=1), page([checkpoint()], has_more=0), page([checkpoint()], offset=True), page([checkpoint()], limit=True), page([1])):
            client, http = self.client(bad)
            with self.subTest(bad=bad), self.assertRaises(SailboxError): client.list_checkpoints()
            self.assertEqual(len(http.calls), 1)

    def test_oversized_page_count_or_native_offset_exhaustion_refuses(self):
        client, http = self.client(page([checkpoint(), checkpoint(CP2)], limit=1))
        with self.assertRaises(SailboxError): client.list_checkpoints(limit=1)
        client, http = self.client(page([checkpoint()], limit=1, offset=100000, has_more=True))
        with self.assertRaisesRegex(SailboxError, "offset bound"):
            client.list_checkpoints(limit=1, offset=100000)
        self.assertEqual(len(http.calls), 1)

    def test_incomplete_metadata_shape_refuses_without_adoption(self):
        for field in ("checkpoint_id", "sailbox_id", "app_id", "name", "checkpoint_generation", "created_at", "expires_at"):
            row = checkpoint(); row.pop(field)
            client, _ = self.client(row)
            with self.subTest(field=field), self.assertRaises(SailboxError): client.checkpoint_info(CP)
        for changes in ({"checkpoint_generation": True}, {"checkpoint_generation": -1}, {"name": 3}, {"created_at": ""}, {"expires_at": 0}):
            client, _ = self.client(checkpoint(**changes))
            with self.subTest(changes=changes), self.assertRaises(SailboxError): client.checkpoint_info(CP)

    def test_metadata_transport_disallows_body_raw_and_stream_before_key(self):
        key = Mock(side_effect=AssertionError("key read"))
        transport = Transport(key_source=key, opener=object())
        for kw in ({"body": {}}, {"data": b"x"}, {"raw": True}, {"stream": True}, {"raw_limit": 8}):
            with self.subTest(kw=kw), self.assertRaises(SailboxError):
                transport("GET", "/sailbox-checkpoints", **kw)
        key.assert_not_called()

    def test_exact_metadata_byte_limit_and_one_extra_byte_refusal(self):
        raw = json.dumps(checkpoint()).encode()
        response = Response(raw + b" " * (sailbox._CHECKPOINT_METADATA_LIMIT - len(raw)))
        client, http = self.client(response)
        self.assertEqual(client.checkpoint_info(CP), checkpoint())
        self.assertEqual(response.reads, [sailbox._CHECKPOINT_METADATA_LIMIT + 1]); self.assertTrue(response.closed)
        response = Response(raw + b" " * (sailbox._CHECKPOINT_METADATA_LIMIT + 1 - len(raw)))
        client, http = self.client(response)
        with self.assertRaises(SailboxError) as caught: client.checkpoint_info(CP)
        self.assertEqual(caught.exception.kind, "checkpoint_metadata_too_large"); self.assertTrue(response.closed)

    def test_declared_oversize_and_bad_length_refuse_before_read(self):
        for length in (str(sailbox._CHECKPOINT_METADATA_LIMIT + 1), "9" * 100, "bad", "-1", 2):
            response = Response(b"{}", headers={"Content-Length": length}); client, _ = self.client(response)
            with self.subTest(length=length), self.assertRaises(SailboxError): client.list_checkpoints()
            self.assertEqual(response.reads, []); self.assertTrue(response.closed)

    def test_declared_short_or_long_content_is_transport_unknown(self):
        raw = json.dumps(checkpoint()).encode()
        for length in (len(raw) - 1, len(raw) + 1):
            response = Response(raw, headers={"Content-Length": str(length)}); client, http = self.client(response)
            with self.subTest(length=length), self.assertRaises(SailboxTransportError) as caught: client.checkpoint_info(CP)
            self.assertTrue(caught.exception.transient); self.assertEqual(len(http.calls), 1)

    def test_read_failure_is_sanitized_and_does_not_retry_or_mutate(self):
        for error in (IncompleteRead(b"partial", 20), TimeoutError(SECRET), OSError(SECRET), URLError(TimeoutError(SECRET))):
            response = Response(b"", error=error); client, http = self.client(response)
            with self.subTest(error=type(error).__name__), self.assertRaises(SailboxTransportError) as caught: client.list_checkpoints()
            self.assertNotIn(SECRET, str(caught.exception)); self.assertEqual(len(http.calls), 1); self.assertTrue(response.closed)

    def test_non_json_refuses_and_no_legacy_query_fallback(self):
        client, http = self.client(Response(b"not-json"))
        with self.assertRaisesRegex(SailboxError, "not JSON"): client.list_checkpoints()
        self.assertEqual(len(http.calls), 1)


if __name__ == "__main__":
    unittest.main()
