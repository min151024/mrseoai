from serpapi import GoogleSearch

params = {
    "q": "ChatGPT",
    "location": "Japan",
    "api_key": "4ab26ee1f5d0c2e92c5f4515df09bb7cec2529632b49fea3f06443588ac6f701"
}

search = GoogleSearch(params)
results = search.get_dict()
print(results)
