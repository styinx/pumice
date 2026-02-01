from datetime import datetime as dt

now = dt.now()

__VERSION__ = (0, 1, now.year * 10000 + now.month * 100 + now.day)
