from web_search import web_search

query = "What is the capital of France?"
results = web_search(query)
for i, result in enumerate(results, 1):
    print(f"{i}. {result}")
