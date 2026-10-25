"""Tests for kosync. Standard library only:  python3 -m unittest discover tests"""

import importlib.machinery
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("kosync", str(ROOT / "kosync"))
_spec = importlib.util.spec_from_loader("kosync", _loader)
kosync = importlib.util.module_from_spec(_spec)
_loader.exec_module(kosync)


SIDECAR = r'''-- we can read Lua syntax here!
return {
    ["annotations"] = {
        [1] = {
            ["chapter"] = "Chapter II",
            ["datetime"] = "2026-09-01 21:10:05",
            ["pageno"] = 21,
            ["pos0"] = "/body/DocFragment[4]/body/p[4]/text().0",
            ["pos1"] = "/body/DocFragment[4]/body/p[4]/text().80",
            ["text"] = "Welcome to my house! Come freely.\
Go safely.",
            ["note"] = "the \"invitation\" rule",
        },
        [2] = {
            ["chapter"] = "Chapter III",
            ["datetime"] = "2026-09-02 08:00:00",
            ["page"] = "/body/DocFragment[5]/body/p[1]/text().0",
            ["pageno"] = 30,
        },
    },
    ["doc_props"] = { ["authors"] = "Bram Stoker", ["title"] = "Dracula" },
    ["partial_md5_checksum"] = "aaaa1111",
    ["percent_finished"] = 0.4321,
    ["summary"] = { ["status"] = "reading", ["modified"] = "2026-09-02" },
    plain_key = -12, hexval = 0x1F, sci = 1.5e3, flag = true, nothing = nil,
    "first", "second";
}
'''


def make_library(path, books):
    """A minimal Calibre metadata.db: just the tables kosync reads."""
    con = sqlite3.connect(path / "metadata.db")
    con.executescript("""
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_authors_link (book INTEGER, author INTEGER);
        CREATE TABLE custom_columns (label TEXT);
    """)
    for book_id, title, author in books:
        con.execute("INSERT INTO books VALUES (?, ?)", (book_id, title))
        con.execute("INSERT INTO authors VALUES (?, ?)", (book_id, author))
        con.execute("INSERT INTO books_authors_link VALUES (?, ?)", (book_id, book_id))
    con.commit()
    con.close()


class LuaParserTest(unittest.TestCase):
    def setUp(self):
        self.data = kosync.parse_lua(SIDECAR)

    def test_strings_and_escapes(self):
        first = self.data["annotations"][1]
        # string.format("%q") writes a newline as a backslash and a real newline.
        self.assertEqual(first["text"], "Welcome to my house! Come freely.\nGo safely.")
        self.assertEqual(first["note"], 'the "invitation" rule')
        self.assertEqual(kosync.parse_lua(r'return { "a\9b" }')[1], "a\tb")  # a decimal escape (%q writes control bytes so)

    def test_numbers_booleans_nil_and_bare_keys(self):
        self.assertEqual(self.data["percent_finished"], 0.4321)
        self.assertEqual(self.data["plain_key"], -12)
        self.assertEqual(self.data["hexval"], 31)
        self.assertEqual(self.data["sci"], 1500.0)
        self.assertIs(self.data["flag"], True)
        self.assertIsNone(self.data["nothing"])

    def test_sequences(self):
        self.assertEqual(kosync.lua_array(self.data["annotations"])[1]["pageno"], 30)
        self.assertEqual((self.data[1], self.data[2]), ("first", "second"))

    def test_errors(self):
        with self.assertRaises(kosync.LuaError):
            kosync.parse_lua("{ no return here }")
        with self.assertRaises(kosync.LuaError):
            kosync.parse_lua('return { ["a"] = "unterminated }')


class AnnotationsTest(unittest.TestCase):
    def test_highlights_have_a_range_bookmarks_do_not(self):
        anns = kosync.lua_array(kosync.parse_lua(SIDECAR)["annotations"])
        highlights, bookmarks = kosync.split_annotations(anns)
        self.assertEqual([a["pageno"] for a in highlights], [21])
        self.assertEqual([a["pageno"] for a in bookmarks], [30])

    def test_rendering_escapes_html(self):
        html = kosync.render_highlights([{"pos0": "a", "pos1": "b", "text": "<b>x</b> & y", "chapter": "One", "pageno": 3}])
        self.assertIn("&lt;b&gt;x&lt;/b&gt; &amp; y", html)
        self.assertIn("<h4>One</h4>", html)


class NamesTest(unittest.TestCase):
    def test_normalise(self):
        self.assertEqual(kosync.normalise("The Café & Bar_Book"), "cafe and bar book")
        self.assertEqual(kosync.short_title("Animal Farm: A Fairy Story"), "animal farm")

    def test_authors_agree_across_spellings(self):
        a = kosync.author_tokens("Fyodor Dostoyevsky")
        self.assertTrue(kosync.authors_agree(a, kosync.author_tokens("Fyodor Dostoevsky")))
        self.assertFalse(kosync.authors_agree(a, kosync.author_tokens("George Orwell")))
        self.assertTrue(kosync.authors_agree(set(), a))  # unknown never blocks

    def test_calibre_device_filename(self):
        rec = {"title": "", "authors": "", "sdr_name": "Crime and Punishment - Fyodor Dostoyevsky (1435).sdr"}
        self.assertEqual(kosync.name_candidates(rec), [("Crime and Punishment", "Fyodor Dostoyevsky")])


class CalibreIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        lib = Path(self.tmp.name)
        make_library(lib, [
            (88, "Dracula", "Bram Stoker"),
            (446, "Crime and Punishment", "Fyodor Dostoevsky"),
            (526, "Animal Farm: A Fairy Story", "George Orwell"),
            (1435, "How to Fix Everything For Dummies", "Gary Hedstrom"),
        ])
        self.index = kosync.CalibreIndex(lib)

    def tearDown(self):
        self.tmp.cleanup()

    def test_title_matching(self):
        self.assertEqual(self.index.match("Dracula", "Bram Stoker")[0], 88)
        self.assertEqual(self.index.match("Animal Farm", "George Orwell")[:3:2], (526, "title-stem"))
        self.assertEqual(self.index.match("Crime & Punishment", "Dostoyevsky")[0], 446)
        self.assertIsNone(self.index.match("Dracula", "George Orwell")[0])  # authors disagree
        self.assertEqual(self.index.match_loose("Dracula-Bram-Stoker")[0], 88)

    def test_a_reused_calibre_id_is_not_trusted(self):
        # The sidecar was named when Crime and Punishment had id 1435; that id now
        # belongs to another book, so it must not be accepted.
        rec = {"title": "Crime and Punishment", "authors": "Fyodor Dostoyevsky",
               "sdr_name": "Crime and Punishment - Fyodor Dostoyevsky (1435).sdr"}
        self.assertFalse(self.index.confirms(1435, kosync.name_candidates(rec)))
        self.assertTrue(self.index.confirms(446, kosync.name_candidates(rec)))
        # A truncated filename title still confirms its own id.
        cut = {"title": "", "authors": "George Orwell", "sdr_name": "Animal Farm_ A Fairy - George Orwell (526).sdr"}
        self.assertTrue(self.index.confirms(526, kosync.name_candidates(cut)))


class FieldsTest(unittest.TestCase):
    def test_build_fields(self):
        rec = {"percent": 0.4321, "status": "reading", "location": "/body/p[2]", "rating": 4, "review": "Good <b>",
               "annotations": kosync.lua_array(kosync.parse_lua(SIDECAR)["annotations"]),
               "stats": {"read_time": 7260, "read_pages": 95, "first_session": 1756750000}, "source": "sidecar"}
        f = kosync.build_fields(rec)
        self.assertEqual((f["ko_progfloat"], f["ko_progint"], f["ko_status"], f["ko_statusbool"]), (43.21, 43, "reading", "false"))
        self.assertEqual((f["ko_readtime"], f["ko_readpages"], f["__rating__"]), (121, 95, 8))
        self.assertIn("&lt;b&gt;", f["ko_review"])
        self.assertIn("koreader_highlights", f)
        self.assertIn("ko_bookmarks", f)
        self.assertNotIn("ko_finish", f)

    def test_complete_means_100_percent_and_a_finish_date(self):
        f = kosync.build_fields({"percent": 0.97, "status": "complete", "modified": "2026-10-01",
                                 "annotations": [], "stats": {}, "source": "sidecar"})
        self.assertEqual((f["ko_progint"], f["ko_statusbool"], f["ko_finish"][:10]), (100, "true", "2026-10-01"))

    def test_min_seconds_only_drops_statistics_only_records(self):
        stats_only = {"source": "stats", "annotations": [], "stats": {"read_time": 30, "read_pages": 1}}
        self.assertEqual(kosync.build_fields(stats_only, min_seconds=60), {})
        self.assertTrue(kosync.build_fields(stats_only, min_seconds=0))

    def test_merge_fields(self):
        merged = kosync.merge_fields({"ko_readtime": 10, "ko_start": "2026-02-01T00:00:00", "ko_review": "short"},
                                     {"ko_readtime": 30, "ko_start": "2026-01-01T00:00:00", "ko_review": "a longer review"})
        self.assertEqual(merged, {"ko_readtime": 30, "ko_start": "2026-01-01T00:00:00", "ko_review": "a longer review"})


class DeviceTest(unittest.TestCase):
    def test_staging_and_statistics(self):
        with tempfile.TemporaryDirectory() as tmp:
            dev, stage = Path(tmp) / "dev", Path(tmp) / "stage"
            sdr = dev / "documents" / "Dracula - Bram Stoker (88).sdr"
            sdr.mkdir(parents=True)
            (sdr / "metadata.epub.lua").write_text(SIDECAR)
            (dev / "documents" / "Dracula - Bram Stoker (88).epub").write_bytes(b"PK")
            (dev / "koreader" / "settings").mkdir(parents=True)
            con = sqlite3.connect(dev / "koreader" / "settings" / "statistics.sqlite3")
            con.executescript("""
                CREATE TABLE book (id INTEGER PRIMARY KEY, title TEXT, authors TEXT, notes INTEGER, last_open INTEGER,
                                   highlights INTEGER, pages INTEGER, md5 TEXT, total_read_time INTEGER, total_read_pages INTEGER);
                CREATE TABLE page_stat_data (id_book INTEGER, page INTEGER, start_time INTEGER, duration INTEGER);
                INSERT INTO book VALUES (1, 'Dracula', 'Bram Stoker', 0, 0, 1, 400, 'aaaa1111', 7260, 95);
                INSERT INTO book VALUES (2, 'Daily News', '', 0, 0, 0, 10, 'dddd4444', 300, 4);
                INSERT INTO page_stat_data VALUES (1, 1, 1756750000, 60), (2, 1, 1760900000, 60);
            """)
            con.commit()
            con.close()

            stats_db, sidecars = kosync.stage_device_files(dev, stage)
            records = kosync.build_records(sidecars, kosync.load_statistics(stats_db))
            by_md5 = {r["md5"]: r for r in records}
            self.assertEqual(by_md5["aaaa1111"]["source"], "sidecar")
            self.assertEqual(by_md5["aaaa1111"]["stats"]["read_time"], 7260)
            self.assertEqual(by_md5["aaaa1111"]["device_file"].name, "Dracula - Bram Stoker (88).epub")
            self.assertEqual(by_md5["dddd4444"]["source"], "stats")  # read, but its sidecar is gone


if __name__ == "__main__":
    unittest.main()
