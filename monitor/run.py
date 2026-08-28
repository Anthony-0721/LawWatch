import argparse
import json
import sys
from pathlib import Path

from .config import load_sites
from .discovery import discover_for_site, is_list_candidate
from .fetcher import BrowserFetcher, HttpFetcher
from .notify import notify_all, send_test_notification
from .state import StateStore


def run(send: bool = False, max_pages: int = 30, persist: bool = True) -> dict:
    sites = load_sites()
    store = StateStore(Path(__file__).resolve().parent / "state.json")
    all_documents = []
    all_errors = {}
    list_urls = store.data.get("list_urls", {})
    any_site_ok = False

    browser_fetcher = BrowserFetcher() if any(site.dynamic for site in sites) else None
    try:
        for site in sites:
            try:
                fetcher = browser_fetcher if site.dynamic else HttpFetcher()
                known = tuple(url for url in list_urls.get(site.url, []) if is_list_candidate(url, ""))
                documents, discovered, errors = discover_for_site(
                    site, fetcher, known_list_urls=known, max_pages=max_pages
                )
                if not errors:
                    any_site_ok = True
                list_urls[site.url] = [url for url in discovered if is_list_candidate(url, "")]
                all_documents.extend(documents)
                all_errors.update(errors)
            except Exception as exc:
                all_errors[site.url] = str(exc)
    finally:
        if browser_fetcher is not None:
            browser_fetcher.close()

    new_items, baseline = store.update(all_documents, all_errors, sites_ok=any_site_ok)
    store.data["list_urls"] = list_urls

    notifications_ok = True
    if new_items and send and not baseline:
        notifications_ok = notify_all(new_items)

    persisted = False
    if persist and notifications_ok:
        store.save()
        persisted = True

    summary = {
        "sites": len(sites),
        "documents": len(all_documents),
        "new_count": len(new_items),
        "baseline": baseline,
        "errors": len(all_errors),
        "notifications_ok": notifications_ok,
        "persisted": persisted,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if not persist:
        would_notify = bool(new_items and send and not baseline)
        print(
            "dry run: state was NOT persisted; "
            f"baseline={baseline}, would_notify={would_notify}, new_items={len(new_items)}",
            file=sys.stderr,
        )
    elif not notifications_ok:
        print(
            "notification failure: no configured channel succeeded; dedup state was NOT saved. "
            "The batch will be retried on the next run.",
            file=sys.stderr,
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--test-notification", action="store_true")
    args = parser.parse_args()
    if args.test_notification:
        ok = send_test_notification()
        print(json.dumps({"test_notification": ok}))
        return 0 if ok else 1
    result = run(
        send=args.send and not args.dry_run,
        max_pages=args.max_pages,
        persist=not args.dry_run,
    )
    if result.get("notifications_ok") is False:
        print("monitor: notifications failed; exiting with status 1", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())