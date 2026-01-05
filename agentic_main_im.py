import os
import time
import pandas as pd
from serpapi import GoogleSearch
from dotenv import load_dotenv
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END


# ENV

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
LOCATION = "Noida, Uttar Pradesh, India"
MAX_RESULTS = 50
NUM_PAGES = 5


# UTILITIES (UNCHANGED LOGIC)

def extract_domain(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    url = url.lower().replace("http://", "").replace("https://", "").replace("www.", "")
    return url.split("/")[0]

def search_google(keyword: str, page: int = 0) -> dict:
    params = {
        "engine": "google",
        "q": keyword,
        "location": LOCATION,
        "api_key": SERPAPI_KEY,
        "num": 10,
        "start": page * 10,
        "gl": "in",
        "hl": "en"
    }
    return GoogleSearch(params).get_dict()


# GOOGLE SEARCH (ORGANIC)

def find_google_search_rank(keyword: str, target_website: str) -> Optional[int]:
    target_domain = extract_domain(target_website)
    current_rank = 0

    for page in range(NUM_PAGES):
        results = search_google(keyword, page)
        organic = results.get("organic_results", [])

        for res in organic:
            link = res.get("link", "")
            if not link:
                continue

            current_rank += 1
            if current_rank > MAX_RESULTS:
                return None

            if target_domain in extract_domain(link):
                return current_rank

        time.sleep(1)

    return None


# GOOGLE PLACES (HYBRID)

def find_google_places_rank(keyword: str, target_website: str) -> Optional[int]:
    target_domain = extract_domain(target_website)

    # 1️⃣ Google Maps
    try:
        maps_params = {
            "engine": "google_maps",
            "q": keyword,
            "location": LOCATION,
            "api_key": SERPAPI_KEY
        }
        maps_results = GoogleSearch(maps_params).get_dict()
        places = maps_results.get("local_results", [])
    except Exception:
        places = []

    # 2️⃣ Local Finder fallback
    if not places:
        try:
            lcl_params = {
                "engine": "google",
                "q": keyword,
                "tbm": "lcl",
                "location": LOCATION,
                "z": 14,
                "hl": "en",
                "gl": "in",
                "api_key": SERPAPI_KEY
            }
            lcl_results = GoogleSearch(lcl_params).get_dict()
            places = lcl_results.get("local_results", [])
        except Exception:
            places = []

    if not places:
        return None

    for idx, place in enumerate(places, start=1):
        title = place.get("title", "").lower()
        website = place.get("website", "").lower()

        if (
            "omkitchen" in title
            or "om kitchen" in title
            or target_domain in website
        ):
            return idx

    return None


# LANGGRAPH STATE

class RankState(TypedDict):
    dataframe: pd.DataFrame
    row_index: int


# AGENTS

def places_rank_agent(state: RankState):
    df = state["dataframe"]
    i = state["row_index"]

    keyword = df.at[i, "Keyword"]
    website = df.at[i, "Website"]

    rank = find_google_places_rank(keyword, website)
    df.at[i, "Google Places Rank"] = rank if rank else "Not in top 50"

    return {"dataframe": df, "row_index": i}

def search_rank_agent(state: RankState):
    df = state["dataframe"]
    i = state["row_index"]

    keyword = df.at[i, "Keyword"]
    website = df.at[i, "Website"]

    rank = find_google_search_rank(keyword, website)
    df.at[i, "Google Search Rank"] = rank if rank else "Not in top 50"

    return {"dataframe": df, "row_index": i}


# GRAPH DEFINITION

graph = StateGraph(RankState)

graph.add_node("places_rank_agent", places_rank_agent)
graph.add_node("search_rank_agent", search_rank_agent)

graph.set_entry_point("places_rank_agent")
graph.add_edge("places_rank_agent", "search_rank_agent")
graph.add_edge("search_rank_agent", END)

ranking_graph = graph.compile()


# RUNNER

def run_agentic_pipeline(input_file: str, output_file: str):
    df = pd.read_excel(input_file)

    df["Google Places Rank"] = None
    df["Google Search Rank"] = None

    for i in range(len(df)):
        print(f"[{i+1}/{len(df)}] {df.at[i, 'Keyword']}")

        ranking_graph.invoke({
            "dataframe": df,
            "row_index": i
        })

        time.sleep(1)

    df.to_excel(output_file, index=False)
    print(f"\n✅ Agentic ranking completed → {output_file}")


# MAIN
if __name__ == "__main__":
    INPUT_FILE = "Ranking_Website.xlsx"
    OUTPUT_FILE = "Agentic_Ranking_Website_Results.xlsx"

    if not SERPAPI_KEY:
        print("❌ SERPAPI_API_KEY missing")
        exit(1)

    run_agentic_pipeline(INPUT_FILE, OUTPUT_FILE)
