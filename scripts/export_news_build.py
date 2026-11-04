"""Refresh the validated news snapshot for hosted builds when explicitly configured."""
import os
from news_engine import export_public
from news_store import NewsStore
from news_rss import write_feed

if os.environ.get("NEWS_BUILD_SYNC") == "1":
    store = NewsStore(backend="supabase")
    try:
        print(export_public(store))
    finally:
        store.close()
else:
    print("News build uses the existing validated snapshot (NEWS_BUILD_SYNC is not enabled).")

print(write_feed(site=os.environ.get('SITE_URL', 'https://elbilsagenten.se')))
