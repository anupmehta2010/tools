CASES = [
    {"args": ["crypto", "uuid"], "contains": ["-"], "rc": 0},
    {"args": ["crypto", "password", "--length", "20"], "rc": 0},
    {"args": ["crypto", "caesar", "abc", "--shift", "3"], "contains": ["def"], "rc": 0},
]
