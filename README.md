# HiAnime Scraper

A Python asynchronous scraper that fetches anime metadata from HiAnime and AniList APIs, then inserts the data into a Supabase database.  
It uses `httpx` for async HTTP requests and `rich` for console logging and progress display.

---

## Features

- Scrapes paginated anime lists from HiAnime.
- Retrieves detailed anime metadata from AniList GraphQL API.
- Cleans and normalizes anime titles before querying AniList.
- Inserts anime, seasons, and episodes into Supabase tables.
- Handles retries and HTTP errors gracefully.
- Logs progress and errors with colored console output.
- Avoids duplicate anime insertion by tracking seen titles.
- Supports asynchronous concurrency for improved performance.

---

## Prerequisites

- Python 3.8+
- Supabase project with tables: `Anime`, `AnimeSeason`, `AnimeEpisode` configured.
- AniList API access (public GraphQL endpoint).
- HiAnime API base URL.

---

## Installation

```bash
pip install httpx rich
