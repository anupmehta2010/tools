CASES = [
    {"args": ["embedded", "crc16", "--hex", "313233343536373839"],
     "contains": ["0x29b1"], "rc": 0},
    {"args": ["embedded", "crc32", "--hex", "313233343536373839"],
     "contains": ["0xcbf43926"], "rc": 0},
    {"args": ["embedded", "crc8", "--hex", "313233343536373839"],
     "contains": ["0xf4"], "rc": 0},
]
