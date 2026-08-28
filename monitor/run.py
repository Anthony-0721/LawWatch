import argparse
import json
from pathlib import Path

from .config import load_sites
from .discovery import discover_for_site, is_list_candidate
from .fetcher import BrowserFetcher, HttpFetcher
from .notify import notify_all
from .state import StateStore


def run(send: bool = False, max_pages: int = 30) -> dict:
    sites = load_sites()
    store = StateStore(Path(__file__).resolve().parent / "state.json")
    all_documents = []
    all_errors = {}
    list_urls = store.data.get("list_urls", {})

    for site in sites:
        try:
            fetcher = BrowserFetcher() if site.dynamic else HttpFetcher()
            known = tuple(url for url in list_urls.get(site.url, []) if is_list_candidate(url, ""))
            documents, discovered, errors = discover_for_site(
                site, fetcher, known_list_urls=known, max_pages=max_pages
            )
            list_urls[site.url] = [url for url in discovered if is_list_candidate(url, "")]
            all_documents.extend(documents)
            all_errors.update(errors)
        except Exception as exc:
            all_errors[site.url] = str(exc)

    new_items, baseline = store.update(all_documents, all_errors)
    store.data["list_urls"] = list_urls
    store.save()
    if new_items and send and not baseline:
        notify_all(new_items)

    summary = {
        "sites": len(sites),
        "documents": len(all_documents),
        "new_count": len(new_items),
        "baseline": baseline,
        "errors": len(all_errors),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-pages", type=int, default=30)
    args = parser.parse_args()
    run(send=args.send and not args.dry_run, max_pages=args.max_pages)
