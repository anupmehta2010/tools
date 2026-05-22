CASES = [
    {"args": ["dev", "calc", "2 + 2 * 5"], "contains": ["12"], "rc": 0},
    {"args": ["dev", "base", "255", "--to-base", "16"], "contains": ["ff"], "rc": 0},
    {"args": ["dev", "slug", "Hello, World!"], "contains": ["hello-world"], "rc": 0},
    {"args": ["dev", "semver-bump", "1.2.3", "--bump", "minor"], "contains": ["1.3.0"], "rc": 0},
    {"args": ["dev", "timestamp", "0"], "contains": ["1970-01-01T00:00:00", "Unix:"], "rc": 0},
]
