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

    def test_free_x_media_feed_keeps_provenance_not_fake_metrics(self):
        rss = b'<rss><channel><item><title>Gameplay footage</title><link>https://fxtwitter.com/gamedev/status/987</link><pubDate>Sat, 14 Nov 2026 02:30:00 GMT</pubDate></item></channel></rss>'
        signals = monitor.fx_x_media_signals(rss, "gamedev")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["url"], "https://x.com/gamedev/status/987")
        self.assertIsNone(signals[0]["likes"])
        self.assertIsNone(signals[0]["reposts"])
        self.assertIsNone(monitor.eligible(signals[0], None))

    def test_fx_x_search_proxy_metrics_are_not_fabricated(self):
        sample = {"type": "status", "id": "123456789", "url": "https://twitter.com/test/status/123456789",
                  "created_at": monitor.iso(), "text": "I made a game prototype with physics and videos",
                  "author": {"screen_name": "test"}, "likes": 5000, "reposts": 600,
                  "media": {"videos": [{"url": "https://example.org/video.mp4"}]}}
        p = monitor.fx_x_search_signal(sample)
        self.assertEqual(p["url"], "https://x.com/test/status/123456789")
        self.assertEqual(p["likes"], 5000)
        self.assertEqual(p["reposts"], 600)
        self.assertTrue(p["video"])
        self.assertEqual(p["counts_source"], "FxEmbed public X proxy, not X official API")
        self.assertEqual(monitor.eligible(p, None), "x_proxy_large_engagement")

    def test_non_game_x_search_is_not_an_auto_alert(self):
        sample = {"type": "status", "id": "123", "url": "https://x.com/test/status/123",
                  "created_at": monitor.iso(), "text": "IGF judges announce a game development policy",
                  "author": {"screen_name": "test"}, "likes": 50000, "reposts": 10000}
        self.assertIsNone(monitor.fx_x_search_signal(sample))

    def test_state_pruning_to_keep_github_readable(self):
        state = {"posts": {"https://bsky.app/profile/x/post/" + str(i): {"last_seen": str(i), "alerted": False} for i in range(1000)}, "runs": []}
        monitor.update(state, [])
        self.assertLessEqual(len(state["posts"]), 650)

    def test_international_creator_post_filter(self):
        self.assertTrue(monitor.relevant("Hice un juego donde puedes saltar entre edificios"))
        self.assertTrue(monitor.relevant("Estoy haciendo un juego de física"))
        self.assertTrue(monitor.relevant("Fiz um jogo com personagens que voam"))
        self.assertTrue(monitor.relevant("Je développe un jeu de puzzle"))
        self.assertTrue(monitor.relevant("Mein neues Spiel mit Physik"))
        self.assertTrue(monitor.relevant("게임을 만들었습니다. 캐릭터가 벽을 부숩니다"))
        self.assertTrue(monitor.relevant("我做了个游戏，可以破坏房间"))
        self.assertTrue(monitor.relevant("独立游戏开发，一款物理游戏"))
        self.assertTrue(monitor.relevant("Here's the gameplay footage for my new game"))
        self.assertTrue(monitor.relevant("I built a game about transforming into anything"))

    def test_international_non_game_posts_excluded(self):
        self.assertFalse(monitor.relevant("Los salarios de desarrolladores de videojuegos son bajos"))
        self.assertFalse(monitor.relevant("ゲーム開発カンファレンスで審査員が声明"))
        self.assertFalse(monitor.relevant("IGF jurors reveal a new game award rule"))

    def test_all_languages_have_dedicated_query_pools(self):
        self.assertGreaterEqual(len(monitor.FX_X_SEARCH_EN), 20)
        self.assertGreaterEqual(len(monitor.FX_X_SEARCH_JP), 6)
        for name in ("FX_X_SEARCH_ES", "FX_X_SEARCH_KO", "FX_X_SEARCH_ZH", "FX_X_SEARCH_EU"):
            self.assertGreaterEqual(len(getattr(monitor, name)), 4)

    def test_overseas_independent_discovery_anchors(self):
        self.assertGreaterEqual(len(monitor.FX_X_GLOBAL_VISUAL_QUERIES), 8)
        self.assertGreaterEqual(len(monitor.FX_X_GLOBAL_CREATORS), 12)
        self.assertTrue(all("filter:videos" in q for q in monitor.FX_X_GLOBAL_VISUAL_QUERIES))
        self.assertTrue({"ebbyamir", "felixrieseberg", "BlendiByl", "apekshik"}.issubset(
            set(monitor.FX_X_GLOBAL_CREATORS)))
        self.assertTrue(monitor.relevant("My new game: a bike ride through a living painting"))
        self.assertTrue(monitor.relevant("Game prototype footage: a destructible skyscraper"))

    def test_deduplicated_alert(self):
        p={"url":"https://bsky.app/profile/a/post/b", "title":"physics game", "text":"physics game", "published": monitor.iso(), "source":"bluesky", "author":"a", "likes":950, "reposts":250, "replies":1, "video":True, "image":False,"x_posts":[]}
        state={"posts": {}, "runs": []}
        first, _=monitor.update(state,[p,p])
        second, _=monitor.update(state,[p])
        self.assertEqual(len(first),1)
        self.assertEqual(len(second),0)

if __name__ == "__main__":
    unittest.main()
