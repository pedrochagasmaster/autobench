from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


DOCUMENT = Path("docs/autobench-onboarding.html")
EXPECTED_PAGES = {
    "onboarding",
    "setup-support",
    "faq",
    "presets-config",
    "advanced-optimization",
    "privacy-outputs",
    "cli-cookbook",
    "large-data",
    "glossary",
}


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.page_languages: list[tuple[str, str]] = []
        self.hrefs: list[str] = []
        self.downloads: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        if values.get("data-page") and values.get("data-lang"):
            self.page_languages.append(
                (str(values["data-page"]), str(values["data-lang"]))
            )
        if tag == "a" and values.get("href"):
            href = str(values["href"])
            self.hrefs.append(href)
            if values.get("download"):
                self.downloads.append((str(values["download"]), href))


def _parse_document() -> tuple[str, _DocumentParser]:
    source = DOCUMENT.read_text(encoding="utf-8")
    parser = _DocumentParser()
    parser.feed(source)
    return source, parser


def test_standalone_onboarding_has_every_page_in_both_languages() -> None:
    _, parser = _parse_document()

    assert len(parser.ids) == len(set(parser.ids))
    assert set(parser.page_languages) == {
        (page, language)
        for page in EXPECTED_PAGES
        for language in ("en", "pt")
    }


def test_standalone_onboarding_has_no_filesystem_document_links() -> None:
    _, parser = _parse_document()

    non_standalone = [
        href
        for href in parser.hrefs
        if not href.startswith(("#", "mailto:", "data:"))
    ]
    assert non_standalone == []


def test_standalone_onboarding_does_not_mutate_browser_history() -> None:
    source = DOCUMENT.read_text(encoding="utf-8")

    assert "history.replaceState" not in source


def test_standalone_onboarding_embeds_named_demo_download() -> None:
    source, parser = _parse_document()

    assert parser.downloads == [
        (
            "autobench_demo.csv",
            next(href for href in parser.hrefs if href.startswith("data:text/csv;base64,")),
        )
    ]
    assert "card_type input_mode card_type_input_mode" in source
    assert "56-row" in source
    assert "56 linhas" in source


def test_standalone_onboarding_records_locked_policy_boundaries() -> None:
    source = DOCUMENT.read_text(encoding="utf-8")

    assert "4/35 has the same output permissions" in source
    assert "4/35 tem as mesmas permissões de saída" in source
    assert "Autobench trusts that decision" in source
    assert "O Autobench confia nessa decisão" in source
    assert "Passing numeric rules does not turn an analysis workbook" in source
    assert "Passar nas regras numéricas não transforma analysis" in source


def test_standalone_onboarding_includes_search_bar() -> None:
    source, parser = _parse_document()

    assert 'id="doc-search"' in source
    assert 'id="doc-search-results"' in source
    assert 'role="search"' in source
    assert 'data-placeholder-en="Search handbook…"' in source
    assert 'data-placeholder-pt="Buscar no manual…"' in source
    assert "buildSearchIndex" in source
    assert "renderSearchResults" in source
    assert "doc-search" in parser.ids
    assert "doc-search-results" in parser.ids
    assert len(parser.ids) == len(set(parser.ids))