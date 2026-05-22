# Download cases. Real downloads need yt-dlp + network (flaky in CI), so the
# catalog sweep covers --help/main([]) and these cases exercise the arg layer
# and the missing-dependency contract without touching the network.
CASES = [
    # Invalid audio codec is rejected by argparse (exit 2) before any yt-dlp
    # import; the error text goes to stderr so we assert only the exit code.
    {"args": ["dl", "audio", "https://example.com", "--format", "zzz"],
     "rc": 2},
]
