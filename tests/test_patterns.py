"""Git-style patterns: .gitignore rules and search filters."""

import pytest

from hermes_scout import patterns


def ignored(gitignore, path, is_dir=False):
    return patterns.is_ignored(patterns.parse_gitignore(gitignore), path, is_dir)


@pytest.mark.parametrize(
    "gitignore,path,is_dir,expected",
    [
        ("*.log", "debug.log", False, True),
        ("*.log", "logs/deep/debug.log", False, True),
        ("*.log", "debug.txt", False, False),
        ("secret.md", "a/b/secret.md", False, True),
        ("/secret.md", "a/secret.md", False, False),
        ("/secret.md", "secret.md", False, True),
        ("docs/draft.md", "docs/draft.md", False, True),
        ("docs/draft.md", "x/docs/draft.md", False, False),
        ("out/", "out", True, True),
        ("out/", "out", False, False),
        ("**/cache", "a/b/cache", True, True),
        ("notes/**", "notes/a/b.md", False, True),
        ("a/**/z.md", "a/z.md", False, True),
        ("a/**/z.md", "a/b/c/z.md", False, True),
        ("file?.md", "file1.md", False, True),
        ("file?.md", "file10.md", False, False),
        ("[ab].md", "a.md", False, True),
        ("[!ab].md", "a.md", False, False),
        ("[!ab].md", "c.md", False, True),
        ("# comment\n\n*.tmp", "x.tmp", False, True),
        ("\\#literal.md", "#literal.md", False, True),
        ("*.md\n!keep.md", "keep.md", False, False),
        ("*.md\n!keep.md", "drop.md", False, True),
        ("[unclosed.md", "[unclosed.md", False, True),
    ],
)
def test_gitignore_rules(gitignore, path, is_dir, expected):
    assert ignored(gitignore, path, is_dir) is expected


def test_nested_rules_only_apply_below_their_folder():
    rules = patterns.parse_gitignore("*.md", base="sub")
    assert patterns.is_ignored(rules, "sub/a.md", False)
    assert not patterns.is_ignored(rules, "a.md", False)
    assert not patterns.is_ignored(rules, "subway/a.md", False)


def test_missing_gitignore_has_no_rules(tmp_path):
    assert patterns.load_gitignore(tmp_path, "") == []


@pytest.mark.parametrize(
    "spec,path,expected",
    [
        ("*.md", "notes/plan.md", True),
        ("*.md", "src/app.py", False),
        ("docs/", "docs/guide/intro.md", True),
        ("docs/", "src/docs.py", False),
        ("src/**/*.py", "src/a/b/app.py", True),
        ("*.md, *.py", "src/app.py", True),
        (["*.txt", "*.py"], "src/app.py", True),
        ("", "anything.md", True),
        (None, "anything.md", True),
    ],
)
def test_path_filter(spec, path, expected):
    assert patterns.PathFilter(spec).matches(path) is expected


def test_empty_path_filter_is_falsy_and_keeps_its_globs():
    assert not patterns.PathFilter(" , ")
    assert patterns.PathFilter("*.md, docs/").globs == ["*.md", "docs/"]
