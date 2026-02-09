import time
import threading
from datetime import datetime, timedelta

class TaskScheduler:
    def __init__(self):
        self.tasks = []

    def add_task(self, command, schedule_time):
        self.tasks.append((command, schedule_time))

    def run(self):
        while True:
            now = datetime.now()
            for command, schedule_time in self.tasks:
                if now >= schedule_time:
                    threading.Thread(target=self.execute_command, args=(command,)).start()
                    self.tasks.remove((command, schedule_time))
            time.sleep(60)

    def execute_command(self, command):
        # Logic to execute the command
        print(f"Executing command: {command}")

scheduler = TaskScheduler()