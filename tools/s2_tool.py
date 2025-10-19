import requests
from langchain.tools import tool

@tool("s2_search", return_direct=False)
def s2_search(query: str) -> str:
    """Search Semantic Scholar for academic papers."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": 3, "fields": "title,authors,year,url"}
    r = requests.get(url, params=params, timeout=30)
    return r.text