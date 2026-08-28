import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .config import load_sites
from .discovery import discover_for_site, is_list_candidate
from .fetcher import BrowserFetcher, HttpFetcher
from .notify import notify_all, send_test_notification
from .state import StateStore

DEFAULT_MAX_WORKERS = 5


def _resolve_workers(max_workers, site_count: int) -> int:
    if max_workers is None:
        env_value = os.getenv("MONITOR_MAX_WORKERS", "").strip()
        max_workers = int(env_value) if env_value.isdigit() else DEFAULT_MAX_WORKERS
    try:
        workers = int(max_workers)
    except (TypeError, ValueError):
        workers = DEFAULT_MAX_WORKERS
    workers = max(1, workers)
    return min(workers, site_count) if site_count else 1


def _crawl_site(site, known_list_urls, max_pages):
    fetcher = BrowserFetcher() if site.dynamic else HttpFetcher()
    try:
        documents, discovered, errors = discover_for_site(
            site, fetcher, known_list_urls=known_list_urls, max_pages=max_pages
        )
        return documents, discovered, errors
    except Exception as exc:
        return [], None, {site.url: str(exc)}
    finally:
        close = getattr(fetcher, "close", None)
        if close is not None:
            close()


def run(
    send: bool = False,
    max_pages: int = 30,
    persist: bool = True,
    max_workers: int | None = None,
) -> dict:
    sites = load_sites()
    store = StateStore(Path(__file__).resolve().parent / "state.json")
    all_documents = []
    all_errors = {}
    list_urls = store.data.get("list_urls", {})
    any_site_ok = False

    results: list[tuple | None] = [None] * len(sites)
    if sites:
        worker_count = _resolve_workers(max_workers, len(sites))
        future_to_index = {}
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            for index, site in enumerate(sites):
                known = tuple(
                    url for url in list_urls.get(site.url, []) if is_list_candidate(url, "")
                )
                future_to_index[pool.submit(_crawl_site, site, known, max_pages)] = index
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as exc:
                    results[index] = ([], None, {sites[index].url: str(exc)})

    for index, site in enumerate(sites):
        documents, discovered, errors = results[index]
        if not errors:
            any_site_ok = True
        if discovered is not None:
            list_urls[site.url] = [url for url in discovered if is_list_candidate(url, "")]
        all_documents.extend(documents)
        all_errors.update(errors)

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
    parser.add_argument("--max-workers", type=int, default=None)
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
        max_workers=args.max_workers,
    )
    if result.get("notifications_ok") is False:
        print("monitor: notifications failed; exiting with status 1", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
