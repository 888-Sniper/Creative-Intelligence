"""Media store tests: upload validation, linking, serving, isolation.

Covers the upload pipeline end to end through the FastAPI app
with CREATIVE_INTEL_MEDIA_DIR pointed at a temp dir, so the repo tree
is never touched.
"""

import base64
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import creative, media, schema

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
JPG = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64 + b"\xff\xd9")
WAV = (b"RIFF" + b"\x00" * 64)
B64PNG = base64.b64encode(PNG).decode()


def make_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    conn.execute(
        "INSERT INTO creatives (creative_key, platform, name)"
        " VALUES (?,?,?)", ("m1", "meta", "M One"))
    conn.commit()
    return conn


class MediaUnitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def test_upload_roundtrip(self):
        rec = media.save_media(self.conn, self.tmp, "m1", "spot.png", B64PNG)
        self.assertEqual(rec["mime"], "image/png")
        self.assertEqual(rec["url"], "/media/%d" % rec["id"])
        blob, mime, _name = media.load_bytes(self.conn, self.tmp, rec["id"])
        self.assertEqual(blob, PNG)
        self.assertEqual(mime, "image/png")

    def test_dedupe_same_bytes(self):
        first = media.save_media(self.conn, self.tmp, "m1", "a.png", B64PNG)
        second = media.save_media(self.conn, self.tmp, "m1", "b.png", B64PNG)
        self.assertEqual(first["id"], second["id"])

    def test_rejects_bad_type_magic_mismatch_key(self):
        with self.assertRaises(ValueError):
            media.save_media(self.conn, self.tmp, "m1", "evil.exe", B64PNG)
        with self.assertRaises(ValueError):
            media.save_media(self.conn, self.tmp, "m1", "fake.png",
                             base64.b64encode(b"not a png").decode())
        for bad in ("../x", "a/b", "", "x" * 200, None):
            with self.assertRaises(ValueError):
                media.save_media(self.conn, self.tmp, bad, "a.png", B64PNG)
        with self.assertRaises(ValueError):
            media.save_media(self.conn, self.tmp, "m1", "a.png",
                             "!!!not-base64!!!")

    def test_mime_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            media.save_media(self.conn, self.tmp, "m1", "a.png", B64PNG,
                             mime="video/mp4")

    def test_source_url_linked_after_annotation(self):
        ann = creative.blank_annotation()
        creative.save_annotation(self.conn, "m1", ann)
        rec = media.save_media(self.conn, self.tmp, "m1", "spot.png", B64PNG)
        got = self.conn.execute("SELECT annotation_json FROM annotations"
                                " WHERE creative_key=?", ("m1",)).fetchone()[0]
        self.assertEqual(json.loads(got)["source_url"], rec["url"])

    def test_upload_before_annotation_links_on_annotate(self):
        rec = media.save_media(self.conn, self.tmp, "m1", "spot.png", B64PNG)
        ann = creative.blank_annotation()
        self.assertFalse(ann.get("source_url"))
        creative.save_annotation(self.conn, "m1", ann)
        got = self.conn.execute("SELECT annotation_json FROM annotations"
                                " WHERE creative_key=?", ("m1",)).fetchone()[0]
        self.assertEqual(json.loads(got)["source_url"], rec["url"])

    def test_existing_source_url_never_overwritten(self):
        first = media.save_media(self.conn, self.tmp, "m1", "a.png", B64PNG)
        ann = creative.blank_annotation()
        creative.save_annotation(self.conn, "m1", ann)
        second = media.save_media(
            self.conn, self.tmp, "m1", "b.jpg",
            base64.b64encode(JPG).decode())
        self.assertNotEqual(first["id"], second["id"])
        got = self.conn.execute("SELECT annotation_json FROM annotations"
                                " WHERE creative_key=?", ("m1",)).fetchone()[0]
        self.assertEqual(json.loads(got)["source_url"], first["url"])

    def test_no_annotation_no_link_no_crash(self):
        rec = media.save_media(self.conn, self.tmp, "m1", "spot.png", B64PNG)
        self.assertTrue(rec["url"].startswith("/media/"))

    def test_find_for_creative_bundle(self):
        media.save_media(self.conn, self.tmp, "m1", "frame.jpg",
                         base64.b64encode(JPG).decode())
        media.save_media(self.conn, self.tmp, "m1", "line.wav",
                         base64.b64encode(WAV).decode())
        bundle = media.find_for_creative(self.conn, self.tmp, "m1")
        self.assertEqual(bundle["images"], [JPG])
        self.assertEqual(bundle["audio"][1], "audio/wav")
        self.assertFalse(bundle["has_video"])

    def test_unknown_id_rejected(self):
        for bad in ("9999", "abc", "../1", "-1"):
            with self.assertRaises(ValueError):
                media.load_bytes(self.conn, self.tmp, bad)


class MediaLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        os.environ["CREATIVE_INTEL_MEDIA_DIR"] = cls._tmp
        cls._db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        conn = sqlite3.connect(cls._db)
        schema.init_db(conn)
        conn.execute("INSERT INTO creatives (creative_key, platform, name)"
                     " VALUES (?,?,?)", ("web1", "tiktok", "Web One"))
        conn.commit()
        conn.close()
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from conftest import make_client, mint_admin
        cls.client = make_client(cls._db)
        cls.client.headers.update(mint_admin(cls._db))

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls._db)
        del os.environ["CREATIVE_INTEL_MEDIA_DIR"]

    def _post(self, path, payload):
        r = self.client.post(path, json=payload)
        return r.status_code, r.json()

    def test_upload_then_serve_roundtrip(self):
        status, rec = self._post("/api/media/upload", {
            "creative_key": "web1", "filename": "clip.png",
            "content_b64": B64PNG})
        self.assertEqual(status, 200)
        r = self.client.get(rec["url"])
        self.assertEqual(r.status_code, 200)
        self.assertIn("image/png", r.headers["content-type"])
        self.assertEqual(r.content, PNG)

    def test_upload_rejects_exe_live(self):
        status, body = self._post("/api/media/upload", {
            "creative_key": "web1", "filename": "evil.exe",
            "content_b64": B64PNG})
        self.assertEqual(status, 409)
        self.assertIn("error", body)

    def test_media_traversal_404(self):
        for bad in ("/media/../Index.html", "/media/abc", "/media/99999"):
            r = self.client.get(bad)
            self.assertEqual(r.status_code, 404, bad)


if __name__ == "__main__":
    unittest.main()
