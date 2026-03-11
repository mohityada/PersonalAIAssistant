import redis
import json
r = redis.Redis(host='localhost', port=6379, db=2)
for key in r.scan_iter("celery-task-meta-*"):
    data = r.get(key)
    if data:
        try:
            task = json.loads(data)
            if task.get("status") == "FAILURE":
                print(f"Failed Task ID: {task.get('task_id')}")
                print(f"Error: {task.get('result')}")
                print(f"Traceback: {task.get('traceback')}")
                print("-" * 40)
        except json.JSONDecodeError:
            pass
