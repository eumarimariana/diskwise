import os
import struct
import tempfile
import time
import unittest
from unittest import mock

from diskwise import actions, duplicates, state as state_mod, trash
from diskwise.config import HOME
from diskwise.describe import describe_folder, known_context
from diskwise.rules import classify
from diskwise.scanner import scan
from diskwise.server import static_file
from diskwise.state import inside, safe_path, state

OLD = time.time() - 900 * 86400


def risk(rel, **kw):
    return classify(os.path.join(HOME, rel), 100, OLD, True, **kw)[0]


class RulesTest(unittest.TestCase):
    def test_credentials_are_dangerous(self):
        self.assertEqual(risk(".ssh/id_rsa"), "danger")
        self.assertEqual(risk(".bashrc"), "danger")
        self.assertEqual(risk("project/.git/objects/ab"), "danger")

    def test_caches_and_installers_are_safe(self):
        self.assertEqual(risk(".cache/mozilla/x.bin"), "safe")
        self.assertEqual(risk("proj/node_modules/a.js"), "safe")
        self.assertEqual(risk("Downloads/vscode.deb"), "safe")

    def test_personal_files_need_caution(self):
        self.assertEqual(risk("Documents/thesis.pdf"), "caution")
        self.assertEqual(risk("Documentos/tcc.pdf"), "caution")  # Portuguese folder name
        self.assertEqual(risk("Downloads/photos.zip"), "caution")

    def test_steam_games_are_caution_not_danger(self):
        base = ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/"
        self.assertEqual(risk(base + "common/GRIS/GRIS_Data/x.assets"), "caution")
        self.assertEqual(risk(base + "shadercache/550/x.foz"), "safe")

    def test_rules_ignore_path_above_scan_root(self):
        # a "/tmp" above the scanned root must not mark everything as temporary
        root = "/tmp/some/place"
        self.assertEqual(classify(root + "/photos", root=root)[0], "neutral")

    def test_system_files_are_dangerous(self):
        self.assertEqual(classify("/etc/hosts", 10, OLD, True)[0], "danger")


class DescribeTest(unittest.TestCase):
    def test_context_chain(self):
        p = os.path.join(HOME, ".vscode/extensions/ms-python.vscode-pylance-2026.4.1/dist/.cache")
        labels = [c[1] for c in known_context(p)]
        self.assertEqual(labels[0], "VS Code")
        self.assertIn("extension vscode-pylance", labels)

    def test_hash_named_folder_and_project_markers(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "54bb8fd8bf188addd6f51c90efb8fb20")
            os.mkdir(p)
            for n in ("package.json", "README.md"):
                with open(os.path.join(p, n), "w") as f:
                    f.write("# My cool project\n")
            files = [(n, 20, time.time()) for n in os.listdir(p)]
            text = " ".join(describe_folder(p, files)["lines"])
        self.assertIn("random code", text)
        self.assertIn("JavaScript", text)
        self.assertIn("My cool project", text)


class ScanTest(unittest.TestCase):
    def test_recursive_totals(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "a/b"))
            for rel, size in (("a/x", 100), ("a/b/y", 50), ("z", 7)):
                with open(os.path.join(d, rel), "wb") as f:
                    f.write(b"0" * size)
            data = scan(d)
        self.assertEqual(data["total"], 157)
        self.assertEqual(data["file_count"], 3)
        self.assertEqual(data["_totals"]["a"], [150, 2])
        self.assertEqual(data["_totals"]["a/b"], [50, 1])


class SafePathTest(unittest.TestCase):
    def test_blocks_paths_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            state["root"] = os.path.realpath(d)
            self.assertIsNotNone(safe_path("sub/file"))
            self.assertIsNone(safe_path("../../etc/passwd"))
            self.assertIsNone(safe_path("/etc/passwd"))

    def test_disk_root_as_scan_root(self):
        self.assertTrue(inside("/home/x", "/"))
        self.assertFalse(inside("/homeless", "/home"))


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class FreedesktopTrashTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.t = trash.FreedesktopTrash(use_gio=False, home_trash=os.path.join(self.d, "Trash"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_trash_and_restore_file_and_folder(self):
        f, sub = os.path.join(self.d, "a b%ç.txt"), os.path.join(self.d, "folder")
        write(f, b"hi")
        write(os.path.join(sub, "x"), b"x")
        done, errors = self.t.trash([f, sub])
        self.assertEqual(errors, [])
        self.assertFalse(os.path.exists(f) or os.path.exists(sub))
        restored, errors = self.t.restore(done)
        self.assertEqual((sorted(restored), errors), (sorted([f, sub]), []))
        self.assertTrue(os.path.isfile(os.path.join(sub, "x")))
        self.assertEqual(os.listdir(os.path.join(self.d, "Trash", "info")), [])

    def test_restore_finds_newest_copy_without_hint(self):
        f = os.path.join(self.d, "x.txt")
        write(f, b"old")
        self.t.trash([f])
        write(f, b"new")
        self.t.trash([f])  # same name: becomes x.2.txt inside the Trash
        restored, _ = self.t.restore([(f, None)])
        self.assertEqual(restored, [f])
        with open(f, "rb") as fh:
            self.assertEqual(fh.read(), b"new")

    def test_restore_never_overwrites(self):
        f = os.path.join(self.d, "x.txt")
        write(f, b"1")
        done, _ = self.t.trash([f])
        write(f, b"other")
        restored, errors = self.t.restore(done)
        self.assertEqual(restored, [])
        self.assertIn("already exists", errors[0])


class WindowsRecycleBinTest(unittest.TestCase):
    def test_parse_v1_and_v2(self):
        path = "C:\\Users\\ana\\photo.jpg"
        raw = path.encode("utf-16-le")
        v2 = struct.pack("<qqqi", 2, 10, 123, len(path) + 1) + raw + b"\0\0"
        v1 = struct.pack("<qqq", 1, 10, 456) + raw.ljust(520, b"\0")
        self.assertEqual(trash.parse_recycle_info(v2), (path, 123))
        self.assertEqual(trash.parse_recycle_info(v1), (path, 456))

    def test_restore_from_fake_bin(self):
        with tempfile.TemporaryDirectory() as d:
            b, orig = os.path.join(d, "bin"), os.path.join(d, "doc.txt")
            raw = orig.encode("utf-16-le")
            for suffix, when, content in (("AAA", 1, b"old"), ("BBB", 2, b"new")):
                write(os.path.join(b, f"$I{suffix}.txt"),
                      struct.pack("<qqqi", 2, 4, when, len(orig) + 1) + raw + b"\0\0")
                write(os.path.join(b, f"$R{suffix}.txt"), content)
            restored, errors = trash.WindowsTrash().restore([(orig, None)], bins=[b])
            self.assertEqual((restored, errors), ([orig], []))
            with open(orig, "rb") as fh:
                self.assertEqual(fh.read(), b"new")
            self.assertEqual(sorted(os.listdir(b)), ["$IAAA.txt", "$RAAA.txt"])


class MacTrashTest(unittest.TestCase):
    def test_fallback_move_and_restore(self):
        with tempfile.TemporaryDirectory() as d:
            t = trash.MacTrash(user_trash=os.path.join(d, ".Trash"))
            f = os.path.join(d, "a.txt")
            write(f, b"1")
            with mock.patch("subprocess.run", side_effect=lambda *a, **k: mock.Mock(returncode=1, stdout="")):
                done, errors = t.trash([f])
            self.assertEqual(errors, [])
            self.assertTrue(done[0][1].startswith(os.path.join(d, ".Trash")))
            self.assertEqual(t.restore(done), ([f], []))
            self.assertTrue(os.path.isfile(f))


class UndoTest(unittest.TestCase):
    """Delete and undo end to end, with a test Trash."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(os.path.join(self.tmp.name, "root"))
        write(os.path.join(self.root, "a/x.bin"), b"1" * 100)
        write(os.path.join(self.root, "a/b/y.bin"), b"2" * 50)
        write(os.path.join(self.root, "z.bin"), b"3" * 7)
        data = scan(self.root)
        state.update(data=data, root=data["root"], freed=0, trashed=0)
        state_mod.undo_stack.clear()
        fake = trash.FreedesktopTrash(use_gio=False, home_trash=os.path.join(self.tmp.name, "Trash"))
        self.patch = mock.patch.object(trash, "_backend", fake)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def totals(self, k):
        return state["data"]["_totals"][k]

    def test_undo_single_file(self):
        p = os.path.join(self.root, "a/x.bin")
        r, code = actions.trash_file("a", "x.bin", p)
        self.assertEqual(code, 200)
        self.assertEqual(self.totals("a"), [50, 1])
        self.assertEqual(self.totals("."), [57, 2])
        r, code = actions.undo()
        self.assertEqual((code, r["restored"], r["paths"]), (200, 1, ["a/x.bin"]))
        self.assertTrue(os.path.isfile(p))
        self.assertEqual(self.totals("a"), [150, 2])
        self.assertEqual(self.totals("."), [157, 3])
        self.assertEqual(state["freed"], 0)
        self.assertIsNone(r["undo"])

    def test_undo_whole_folder(self):
        r, code = actions.trash_bulk("a", "tree", False)
        self.assertEqual(code, 200)
        self.assertNotIn("a/b", state["data"]["_totals"])
        r, code = actions.undo(r["undo"]["id"])
        self.assertEqual(code, 200)
        self.assertEqual(self.totals("a"), [150, 2])
        self.assertEqual(self.totals("a/b"), [50, 1])
        self.assertIn("a/b", {f["path"] for f in r["folders"]})

    def test_trash_paths_keeps_one_copy(self):
        r, code = actions.trash_paths(["a/x.bin", "z.bin"], groups=[["a/x.bin", "z.bin"]])
        self.assertEqual(code, 400)
        r, code = actions.trash_paths(["z.bin"], groups=[["a/x.bin", "z.bin"]])
        self.assertEqual((code, r["trashed"]), (200, 1))
        self.assertEqual(self.totals("."), [150, 2])
        r, code = actions.trash_paths(["../outside"])
        self.assertEqual(code, 400)


class DuplicatesTest(unittest.TestCase):
    def test_finds_same_content_only(self):
        with tempfile.TemporaryDirectory() as d:
            big = os.urandom(300_000)
            write(os.path.join(d, "a/photo.jpg"), big)
            write(os.path.join(d, "b/copy.jpg"), big)
            write(os.path.join(d, "b/almost.jpg"), big[:-1] + bytes([big[-1] ^ 1]))  # only the end differs
            mid = big[:100_000]
            write(os.path.join(d, "m1"), mid)
            write(os.path.join(d, "m2"), mid[:-70_000] + b"x" + mid[-69_999:])  # the middle differs
            write(os.path.join(d, "empty1"), b"")
            write(os.path.join(d, "empty2"), b"")
            os.link(os.path.join(d, "a/photo.jpg"), os.path.join(d, "a/hardlink.jpg"))
            groups = duplicates.find_duplicates(scan(d)["_files"], d)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["size"], 300_000)
        self.assertEqual(len(groups[0]["files"]), 2)
        names = {os.path.basename(p) for p, _ in groups[0]["files"]}
        self.assertIn("copy.jpg", names)
        self.assertNotIn("almost.jpg", names)


class StaticFilesTest(unittest.TestCase):
    def test_vendor_files_served_and_no_escape(self):
        self.assertIsNotNone(static_file("vendor/tailwind.js"))
        self.assertIsNotNone(static_file("app.js"))
        self.assertIsNone(static_file("../server.py"))
        self.assertIsNone(static_file("vendor/../../server.py"))


if __name__ == "__main__":
    unittest.main()
