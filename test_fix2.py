import os
import uuid
import time
from app.workers.tasks import ingest_file

file_id = "f3e9223b-e5fd-458a-9dc1-ef0fa83a8511"

result = ingest_file.delay(file_id)
timeout = 15
while timeout > 0:
    if result.ready():
        if result.successful():
            print("SUCCESS")
        else:
            print("FAILURE:", result.result)
        break
    time.sleep(1)
    timeout -= 1
else:
    print("TIMEOUT")
