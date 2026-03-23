import json

# Note the encoding='utf-16' addition here
with open("names.txt", "r", encoding="utf-16") as f:
    raw_content = f.read().split()
    # Filter out headers and junk
    clean_names = [n.lower() for n in raw_content if len(n) > 2 and not n.startswith('-')]

unique_names = sorted(list(set(clean_names)))
print(json.dumps(unique_names, indent=4))