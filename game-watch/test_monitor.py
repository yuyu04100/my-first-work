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
        p = {"uri":"at://did:plc:test/app.bsky.feed.post/abc", "record":{"text":"I made an indie game with physics! https://x.com/a/status/123", "createdAt":monitor.iso()}, "author":{"handle":"test.bsky.social"}, "likeCount":900, "repostCount":120, "replyCount":8, "embed":{"images":[]}}
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
        self.assertFalse(monitor.relevant("loser behaviour to be sending death threats to indie game developers"))
        self.assertFalse(monitor.relevant("I didn't buy the Harry Potter video game"))
        self.assertFalse(monitor.relevant("Pokemon made this animation, I want it to be a real game"))
        self.assertTrue(monitor.relevant("I made a ski jumping game where you jump from falling stocks"))
        self.assertTrue(monitor.relevant("New game prototype: game where you punch through walls"))
        self.assertTrue(monitor.relevant("ゲーム開発中、壁を破壊するゲームを作りました"))
    def test_industry_statement_not_a_game_demo(self):
        self.assertFalse(monitor.relevant("ゲーム開発カンファレンスGDCのIGF審査員チームが声明を公開"))
        self.assertFalse(monitor.relevant("IGF game developer awards jurors announce policy"))
        self.assertTrue(monitor.relevant("I made a game where you punch through a wall"))

    def test_rss_empty_result_is_not_a_verified_x_hit(self):
        self.assertEqual(monitor.rss_item_count(b"<rss><channel></channel></rss>"), 0)
        self.assertEqual(monitor.rss_item_count(b"<rss><channel><item><title>A</title></item></channel></rss>"), 1)

    def test_indexed_x_link_survives_keyword_rejection(self):
        rss = b'<rss><channel><item><title>Random clip</title><link>https://x.com/someone/status/123</link><description>Unlabeled short video</description></item></channel></rss>'
        self.assertEqual(monitor.parse_rss(rss, "bing-x-index"), [])
        leads = monitor.indexed_x_candidates(rss)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["status_url"], "https://x.com/someone/status/123")

    def test_state_pruning_to_keep_github_readable(self):
        state = {"posts": {"https://bsky.app/profile/x/post/" + str(i): {"last_seen": str(i), "alerted": False} for i in range(1000)}, "runs": []}
        monitor.update(state, [])
        self.assertLessEqual(len(state["posts"]), 650)

    def test_deduplicated_alert(self):
        p={"url":"https://bsky.app/profile/a/post/b", "title":"physics game", "text":"physics game", "published": monitor.iso(), "source":"bluesky", "author":"a", "likes":950, "reposts":250, "replies":1, "video":True, "image":False,"x_posts":[]}
        state={"posts": {}, "runs": []}
        first, _=monitor.update(state,[p,p])
        second, _=monitor.update(state,[p])
        self.assertEqual(len(first),1)
        self.assertEqual(len(second),0)

if __name__ == "__main__":
    unittest.main()
