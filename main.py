from AutoGLM_GUI.scheduler import scheduler

def main():
    scheduler_thread = threading.Thread(target=scheduler.run)
    scheduler_thread.start()

    # Example task
    scheduler.add_task("Daily Sign-in", datetime.now() + timedelta(seconds=30))

if __name__ == "__main__":
    main()