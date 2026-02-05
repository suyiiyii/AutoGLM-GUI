from task_manager import TaskManager

def main():
    task_manager = TaskManager()
    # Example task: daily sign-in at 8 AM
    task_manager.add_task(sign_in_task, "08:00")
    task_manager.run_pending()

def sign_in_task():
    print("Performing daily sign-in...")

if __name__ == "__main__":
    main()