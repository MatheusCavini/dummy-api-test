usage_counter = {}

def increment_usage(api_key):
    key = api_key.replace("Bearer ", "")
    usage_counter[key] = usage_counter.get(key, 0) + 1
