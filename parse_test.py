import redis
import json
r = redis.Redis(host='localhost', port=6379, db=2)
for key in r.scan_iter("celery-task-meta-*"):
    data = r.get(key)
    if data:
        try:
            task = json.loads(data)
            if task.get("status") == "FAILURE":
                print(f"Task args: {task.get('args')}")
                print(f"Task kwargs: {task.get('kwargs')}")
        except json.JSONDecodeError:
            pass
