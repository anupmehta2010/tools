CASES = [
    {"args": ["text", "hash", "--algo", "sha256"], "stdin": "abc",
     "contains": ["ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"], "rc": 0},
    {"args": ["text", "b64encode", "hello"], "contains": ["aGVsbG8="], "rc": 0},
    {"args": ["text", "rot13", "hello"], "contains": ["uryyb"], "rc": 0},
    {"args": ["text", "snake"], "stdin": "Hello World", "contains": ["hello_world"], "rc": 0},
]
