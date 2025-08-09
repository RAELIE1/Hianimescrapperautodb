import asyncio
import random
import uuid
import re
from rich.console import Console
from rich.progress import Progress
import httpx

ANIWATCH_BASE = "https://idk"
ANILIST_URL = "https://graphql.anilist.co"

SUPABASE_URL = ""
SUPABASE_KEY = ""

ANILIST_QUERY = """
query ($search: String) {
  Media(search: $search, type: ANIME) {
    id
    title {
      romaji
      english
    }
    coverImage {
      large
    }
    bannerImage
    trailer {
      site
      id
    }
    genres
    episodes
    format
    description
  }
}
"""

console = Console()
seen_titles = set()

def clean_title(title: str) -> str:
    title = title.strip().strip('"').strip('“”')
    title = re.sub(r"\(.*?\)", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title

async def fetch_with_retry(client, method, url, **kwargs):
    max_retries = 3
    retry_delay = 5
    for attempt in range(max_retries):
        try:
            resp = await client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                console.log(f"[yellow]AniList: No match found for request → skipping[/yellow]")
                return None
            if attempt < max_retries - 1:
                wait_time = retry_delay + random.uniform(0, 2)
                console.log(f"[yellow]Request failed, retrying in {wait_time:.1f}s:[/yellow] {e}")
                await asyncio.sleep(wait_time)
            else:
                console.log(f"[red]Request failed after {max_retries} retries:[/red] {e}")
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay + random.uniform(0, 2)
                console.log(f"[yellow]Request failed, retrying in {wait_time:.1f}s:[/yellow] {e}")
                await asyncio.sleep(wait_time)
            else:
                console.log(f"[red]Request failed after {max_retries} retries:[/red] {e}")
                raise

async def fetch_hianime_az(client, sort_option: str, page: int):
    url = f"{ANIWATCH_BASE}/api/v2/hianime/azlist/{sort_option}?page={page}"
    resp = await fetch_with_retry(client, "GET", url)
    return resp.json() if resp else {}

async def fetch_hianime_qtip(client, anime_id: str):
    url = f"{ANIWATCH_BASE}/api/v2/hianime/qtip/{anime_id}"
    resp = await fetch_with_retry(client, "GET", url)
    return resp.json() if resp else {}

async def fetch_anilist(client, title: str):
    cleaned_title = clean_title(title)
    for search_title in [cleaned_title, title]:
        payload = {"query": ANILIST_QUERY, "variables": {"search": search_title}}
        resp = await fetch_with_retry(client, "POST", ANILIST_URL, json=payload)
        if not resp:
            continue
        data = resp.json()
        media = data.get("data", {}).get("Media")
        if media:
            return media
    return None

async def sb_insert(client, table, payload):
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        },
        json=payload
    )
    if resp.status_code >= 400:
        console.log(f"[red]Supabase insert failed for table {table}:[/red] {resp.status_code}")
        try:
            console.log(f"[red]Payload sent:[/red] {payload}")
            console.log(f"[red]Response:[/red] {resp.text}")
        except Exception as e:
            console.log(f"[red]Error reading response text:[/red] {e}")
        resp.raise_for_status()
    return resp.json()

async def scrape_anime():
    async with httpx.AsyncClient(timeout=20) as client:
        page = 1
        sort_option = "all"
        with Progress() as progress:
            task = progress.add_task("[cyan]Scraping HiAnime list...", total=None)
            while True:
                console.log(f"Fetching page {page}...")
                azlist = await fetch_hianime_az(client, sort_option, page)
                results = azlist.get("data", {}).get("animes", [])
                console.log(f"Page {page} results count: {len(results)}")
                if not results:
                    console.log("[green]No more results, ending scrape.[/green]")
                    break
                for entry in results:
                    title = entry["name"]
                    if title in seen_titles:
                        console.log(f"[yellow]Skipping duplicate:[/yellow] {title}")
                        continue
                    seen_titles.add(title)
                    anime_id = entry["id"]
                    try:
                        qtip = await fetch_hianime_qtip(client, anime_id)
                        qdata = qtip.get("data", {}).get("anime", {})
                        al_data = await fetch_anilist(client, title)
                        if not al_data:
                            console.log(f"[red]AniList data not found for:[/red] {title}")
                            continue
                        description = al_data.get("description") or ""
                        anilist_id = int(al_data["id"]) if al_data.get("id") else 0
                        thumb = al_data["coverImage"]["large"] if al_data.get("coverImage") else None
                        genres = al_data.get("genres", [])
                        trailer = None
                        if al_data.get("trailer") and al_data["trailer"]["site"] == "youtube":
                            trailer = f"https://youtu.be/{al_data['trailer']['id']}"
                        anime_payload = {
                            "id": str(uuid.uuid4()),
                            "title": title,
                            "description": description,
                            "anilistId": anilist_id,
                            "genre": ", ".join(genres) if genres else None,
                            "trailerUrl": trailer,
                            "thumbnailUrl": thumb
                        }
                        inserted = await sb_insert(client, "Anime", anime_payload)
                        anime_uuid = inserted[0]["id"]
                        season_payload = {
                            "id": str(uuid.uuid4()),
                            "animeId": anime_uuid,
                            "season": 1
                        }
                        season_insert = await sb_insert(client, "AnimeSeason", season_payload)
                        season_uuid = season_insert[0]["id"]
                        ep_total = qdata.get("episodes", {}).get("sub") or 0
                        console.log(f"Inserting {ep_total} episodes for {title}")
                        for ep_num in range(1, ep_total + 1):
                            episode_payload = {
                                "id": str(uuid.uuid4()),
                                "seasonId": season_uuid,
                                "animeId": anime_uuid,
                                "episode": ep_num
                            }
                            await sb_insert(client, "AnimeEpisode", episode_payload)
                        console.log(f"[blue]Inserted {ep_total} episodes for[/blue] {title}")
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    except Exception as e:
                        console.log(f"[red]Error processing {title}: {e}[/red]")
                        continue
                page += 1
                progress.advance(task)

if __name__ == "__main__":
    asyncio.run(scrape_anime())
