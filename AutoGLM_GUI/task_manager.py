import schedule
import time

class TaskManager:
    def __init__(self):
        self.tasks = []

    def add_task(self, task, trigger_time):
        self.tasks.append((task, trigger_time))
        schedule.every().day.at(trigger_time).do(task)

    def run_pending(self):
        while True:
            schedule.run_pending()
            time.sleep(1)