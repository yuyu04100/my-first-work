import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import monitor

class MonitorTest(unittest.TestCase):
    def test_url_normalization(self):
        self.assertEqual(monitor.normalized_url("https://twitter.com/test/status/123?ref=aa"), "https://x.com/test/status/123")
    def test_bsky_engagement_signal(self):
        p = {"uri":"at://did:plc:test/app.bsky.feed.post/abc", "record":{"text":"I made an indie game with physics! https://x.com/a/status/123", "createdAt":"2026-11-14T02:00:00Z"}, "author":{"handle":"test.bsky.social"}, "likeCount":900, "repostCount":120, "replyCount":8, "embed":{"images":[]}}
        s = monitor.bsky_to_signal(p)
        self.assertEqual(s["url"], "https://bsky.app/profile/test.bsky.social/post/abc")
        self.assertEqual(s["x_posts"], ["https://x.com/a/status/123"])
        self.assertEqual(monitor.eligible(s, None), "large_reposts_or_likes")
    def test_no_x_numbers_are_fabricated(self):
        rss = b'<rss><channel><item><title>Viral game prototype on X</title><link>https://x.com/dev/status/123</link><description>game dev</description><pubDate>Sat, 14 Nov 2026 02:30:00 GMT</pubDate></item></channel></rss>'
        s = monitor.parse_rss(rss, "bing-x-index")[0]
        self.assertIsNone(s["likes"])
        self.assertIsNone(s["reposts"])
        self.assertIsNone(monitor.eligible(s,None))
    def test_generic_unrelated_story_rejected(self):
        self.assertFalse(monitor.relevant("football game tonight"))
    def test_deduplicated_alert(self):
        p={"url":"https://bsky.app/profile/a/post/b", "title":"physics game", "text":"physics game", "published": "2026-11-14T02:00:00Z", "source":"bluesky", "author":"a", "likes":950, "reposts":250, "replies":1, "video":True, "image":False,"x_posts":[]}
        state={"posts": {}, "runs": []}
        first, _=monitor.update(state,[p,p])
        second, _=monitor.update(state,[p])
        self.assertEqual(len(first),1)
        self.assertEqual(len(second),0)

if __name__ == "__main__":
    unittest.main()
