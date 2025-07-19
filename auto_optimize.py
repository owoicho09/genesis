import os
import django
import sys
import time
import logging
from agent.tools.optimization.scheduler import run_optimization

# ✅ Set up Django environment
sys.path.append(os.path.dirname(__file__))  # Add project root to sys.path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')  # ← your actual settings file
django.setup()



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def main_loop():
    while True:
        logging.info("Starting optimization run...")
        try:
            report = run_optimization()
            logging.info(f"Optimization completed: {report}")
        except Exception as e:
            logging.error(f"Error during optimization: {e}")
        logging.info("Sleeping for 1 hour...")
        time.sleep(3600)  # Sleep for 1 hour

if __name__ == "__main__":
    main_loop()