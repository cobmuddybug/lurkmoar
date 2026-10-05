"""Synthetic payloads shaped like the structure probes of the vichan-family sites. No real content."""

VICHAN_CATALOG = [
    {"page": 0, "threads": [
        {"no": 10, "sub": "First &amp; thread", "com": "hello<br>world", "name": "Anonymous", "time": 1000,
         "last_modified": 2000, "replies": 4, "images": 2, "sticky": 1, "locked": 0, "cyclical": "0",
         "tn_w": 200, "tn_h": 100, "w": 800, "h": 400, "fsize": 5000, "filename": "pic", "ext": ".jpg",
         "tim": "1700000000000", "md5": "x", "resto": 0},
        {"no": 11, "com": "no file", "name": "Anonymous", "time": 1100, "replies": 0, "images": 0,
         "sticky": 0, "locked": 1, "resto": 0},
    ]},
    {"page": 1, "threads": [
        {"no": 12, "sub": "Video", "com": "clip", "time": 900, "last_modified": 3000, "replies": 9,
         "images": 3, "ext": ".webm", "tim": "1700000000001-9", "filename": "v", "w": 640, "h": 360,
         "fsize": 99999, "resto": 0},
    ]},
]

VICHAN_THREAD = {"posts": [
    {"no": 10, "resto": 0, "sub": "First", "com": "OP text", "name": "Anonymous", "time": 1000,
     "tim": "1700000000000", "ext": ".jpg", "filename": "pic", "w": 800, "h": 400, "fsize": 5000,
     "tn_w": 200, "tn_h": 100, "md5": "x"},
    {"no": 11, "resto": 10, "name": "Anonymous", "time": 1010,
     "com": "<a onclick=\"highlightReply('10', event);\" href=\"/sec/res/10.html#10\">&gt;&gt;10</a><br>reply"},
    {"no": 12, "resto": 10, "name": "Anon", "trip": "!abc", "capcode": "Admin", "time": 1020,
     "com": "<span class=\"quote\">&gt;green</span>", "tim": "1700000000002-1", "ext": ".png",
     "filename": "a", "w": 10, "h": 10, "fsize": 99,
     "extra_files": [{"tim": "1700000000002-2", "ext": ".gif", "filename": "b", "w": 5, "h": 5, "fsize": 9},
                     {"tim": "1700000000002-3", "ext": ".webm", "filename": "c", "w": 6, "h": 6, "fsize": 8}]},
]}

FILES_CATALOG = [
    {"page": 0, "threads": [
        {"no": 20, "sub": "Files thread", "com": "text", "name": "Anonymous", "time": 1000, "last_modified": 2000,
         "replies": 3, "images": 1, "sticky": 0, "locked": 0, "board": "alt",
         "files": [{"id": "f1", "mime": "image/jpeg", "ext": ".jpg", "w": 10, "h": 10, "fsize": 100,
                    "filename": "p", "tim": "1700000000010-6", "spoiler": False, "md5": "m",
                    "file_path": "/alt/src/1700000000010-6.jpg", "thumb_path": "/alt/thumb/1700000000010-6.webp"}],
         "resto": 0},
        {"no": 21, "com": "no files", "time": 1100, "replies": 0, "images": 0, "board": "leftypol",
         "files": [], "resto": 0},
    ]},
]

FILES_THREAD = {"posts": [
    {"no": 20, "resto": 0, "sub": "Files thread", "com": "OP", "name": "Anonymous", "time": 1000,
     "board": "alt",
     "files": [{"id": "f1", "ext": ".jpg", "w": 10, "h": 10, "fsize": 100, "filename": "p", "spoiler": True,
                "tim": "1700000000010-6", "file_path": "/alt/src/1700000000010-6.jpg",
                "thumb_path": "/alt/thumb/1700000000010-6.webp"},
               {"id": "f2", "ext": ".mp4", "w": 20, "h": 20, "fsize": 200, "filename": "q",
                "tim": "1700000000010-7", "file_path": "/alt/src/1700000000010-7.mp4",
                "thumb_path": "/alt/thumb/1700000000010-7.webp"}]},
    {"no": 21, "resto": 20, "name": "Anonymous", "time": 1010, "com": "reply", "files": []},
]}
