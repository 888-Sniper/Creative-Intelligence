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
        out = video.prepare(still, os.path.join(self.tmp, "cache2"))
        self.assertIsNone(out["audio"])
        self.assertTrue(out["images"])

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
