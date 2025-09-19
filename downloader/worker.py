import os
import redis
from rq import Worker, Queue, Connection

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
conn = redis.from_url(REDIS_URL)

if __name__ == "__main__":
    with Connection(conn):
        qs = ["downloads"]
        worker = Worker(qs)
        worker.work()
