"""Video preprocessing tests: real ffmpeg decomposition of a
synthetic clip (generated on the fly, no fixtures), plus the
no-ffmpeg fail-closed path."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import video

HAVE_FFMPEG = video.have_ffmpeg()


def _cached_audio(cache):
    if not os.path.isdir(cache):
        return []
    return [name for name in os.listdir(cache)
            if name.endswith("_audio.wav") or name.endswith(".partial.wav")]


def _corrupt_mdat(path):
    """Flip every mdat payload byte. The container still opens."""
    data = bytearray(open(path, "rb").read())
    pos = 0
    while pos + 8 <= len(data):
        size = int.from_bytes(data[pos:pos + 4], "big")
        if size < 8:
            break
        if data[pos + 4:pos + 8] == b"mdat":
            for i in range(pos + 8, pos + size):
                data[i] ^= 0xA5
            break
        pos += size
    with open(path, "wb") as fh:
        fh.write(data)


def _data_chunk_size(blob):
    pos = 12
    while pos + 8 <= len(blob):
        size = int.from_bytes(blob[pos + 4:pos + 8], "little")
        if blob[pos:pos + 4] == b"data":
            return size
        pos += 8 + size + (size & 1)
    return None


def make_clip(path, with_audio=True):
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i", "testsrc=duration=2:size=128x128:rate=5"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    cmd += ["-pix_fmt", "yuv420p", "-shortest", path]
    subprocess.run(cmd, check=True, timeout=60)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class DecomposeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clip = os.path.join(self.tmp, "clip.mp4")
        make_clip(self.clip)

    def test_audio_and_frames_extracted(self):
        out = video.prepare(self.clip, os.path.join(self.tmp, "cache"))
        self.assertIsNotNone(out["audio"])
        self.assertTrue(out["audio"][0].startswith(b"RIFF"))
        self.assertEqual(out["audio"][1], "audio/wav")
        self.assertTrue(out["images"])
        for frame in out["images"]:
            self.assertTrue(frame.startswith(b"\xff\xd8\xff"))

    def test_cached_second_run(self):
        cache = os.path.join(self.tmp, "cache")
        first = video.prepare(self.clip, cache)
        second = video.prepare(self.clip, cache)
        self.assertEqual(first["audio"][0], second["audio"][0])
        self.assertEqual(first["images"], second["images"])

    def test_stills_only_clip_still_yields_frames(self):
        still = os.path.join(self.tmp, "still.mp4")
        make_clip(still, with_audio=False)
        cache = os.path.join(self.tmp, "cache2")
        out = video.prepare(still, cache)
        self.assertIsNone(out["audio"])
        self.assertTrue(out["images"])
        self.assertFalse(_cached_audio(cache))

    def test_failed_aac_does_not_leave_a_header_cache(self):
        bad = os.path.join(self.tmp, "bad.mp4")
        shutil.copy(self.clip, bad)
        _corrupt_mdat(bad)
        direct = os.path.join(self.tmp, "direct.wav")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", bad,
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
             direct],
            capture_output=True, timeout=60)
        self.assertNotEqual(proc.returncode, 0)
        blob = open(direct, "rb").read()
        self.assertEqual(
            int.from_bytes(blob[4:8], "little") + 8, len(blob))
        self.assertEqual(_data_chunk_size(blob), 0)
        cache = os.path.join(self.tmp, "bad-cache")
        for _ in range(2):
            with self.assertRaises(Exception) as ctx:
                video.prepare(bad, cache)
            self.assertIn("ffmpeg exited", str(ctx.exception))
            self.assertFalse(_cached_audio(cache))

    def test_duration_probe(self):
        dur = video.probe_duration_s(self.clip)
        self.assertIsNotNone(dur)
        self.assertAlmostEqual(dur, 2.0, delta=0.5)


class NoFfmpegTest(unittest.TestCase):
    def test_missing_binary_fails_closed(self):
        real = shutil.which
        shutil.which = lambda _name: None
        try:
            self.assertFalse(video.have_ffmpeg())
            with self.assertRaises(Exception) as ctx:
                video.prepare("/nonexistent.mp4", tempfile.mkdtemp())
            self.assertIn("ffmpeg", str(ctx.exception))
        finally:
            shutil.which = real


if __name__ == "__main__":
    unittest.main()
