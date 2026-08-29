"""Tests for :mod:`publisher.rules_web.spec`."""

from __future__ import annotations

from pathlib import Path

import pytest

from publisher.rules_web import spec


def _load(tmp_path: Path, text: str) -> spec.Spec:
    """Write ``text`` as a specification file and load it."""
    path = tmp_path / "spec.toml"
    path.write_text(text, encoding="utf-8")
    return spec.load(path)


def test_a_slug_defaults_to_the_filename(tmp_path: Path) -> None:
    """Deriving is the default; the override exists for when derivation is not wanted."""
    loaded = _load(tmp_path, '[[document]]\nfile = "08-vehicles.md"\n')
    assert loaded.documents[0].slug == "vehicles"


def test_an_explicit_slug_wins(tmp_path: Path) -> None:
    """Upstream renumbering a file must not move a public URL, and this is how that is said."""
    loaded = _load(tmp_path, '[[document]]\nfile = "08-vehicles.md"\nslug = "war-machines"\n')
    assert loaded.documents[0].slug == "war-machines"


def test_two_documents_cannot_share_a_slug(tmp_path: Path) -> None:
    """One URL, one document. The second would overwrite the first, silently."""
    text = (
        '[[document]]\nfile = "08-vehicles.md"\nslug = "same"\n'
        '[[document]]\nfile = "09-transport.md"\nslug = "same"\n'
    )
    with pytest.raises(spec.SpecError) as failure:
        _load(tmp_path, text)
    assert "same" in str(failure.value)


def test_a_specification_that_publishes_nothing_fails(tmp_path: Path) -> None:
    """An edition with no documents is a mistake, not an empty site."""
    with pytest.raises(spec.SpecError):
        _load(tmp_path, 'title = "Nothing"\n')


def test_an_unknown_key_fails(tmp_path: Path) -> None:
    """A misspelled key that is ignored looks exactly like a feature that does not work."""
    with pytest.raises(spec.SpecError) as failure:
        _load(tmp_path, '[[document]]\nfile = "08-vehicles.md"\nslugg = "typo"\n')
    assert "slugg" in str(failure.value)


def test_an_unknown_top_level_key_fails(tmp_path: Path) -> None:
    """Same rule at the top of the file."""
    with pytest.raises(spec.SpecError):
        _load(tmp_path, 'languge = "en"\n[[document]]\nfile = "08-vehicles.md"\n')


def test_a_document_without_a_file_fails(tmp_path: Path) -> None:
    """There is nothing to publish without one."""
    with pytest.raises(spec.SpecError) as failure:
        _load(tmp_path, '[[document]]\nslug = "vehicles"\n')
    assert "file" in str(failure.value)


def test_a_document_that_is_not_a_table_fails(tmp_path: Path) -> None:
    """`document` is a list of tables; anything else cannot name a file."""
    with pytest.raises(spec.SpecError):
        spec.from_dict({"document": ["08-vehicles.md"]}, "inline")


def test_a_missing_file_fails(tmp_path: Path) -> None:
    """Named by path, so the message says which one."""
    with pytest.raises(spec.SpecError) as failure:
        spec.load(tmp_path / "absent.toml")
    assert "absent.toml" in str(failure.value)


def test_invalid_toml_fails_with_the_parser_s_reason(tmp_path: Path) -> None:
    """A syntax error is reported where it is, not as a shrug about the whole file."""
    with pytest.raises(spec.SpecError) as failure:
        _load(tmp_path, "this is not toml = = =")
    assert "not valid TOML" in str(failure.value)


def test_the_base_path_is_stripped_of_slashes(tmp_path: Path) -> None:
    """It is joined into paths, so a stray slash would double up in every URL."""
    loaded = _load(tmp_path, 'base_path = "/es/"\n[[document]]\nfile = "08-vehicles.md"\n')
    assert loaded.base_path == "es"
