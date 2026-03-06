
from core.orchestrator import Orchestrator

def main():
    print("--- Initializing AI Research System ---")
    orchestrator = Orchestrator()

    try:
        orchestrator.start()
    except KeyboardInterrupt:
        print("\n--- Keyboard interrupt detected. Shutting down. ---")
    finally:
        orchestrator.shutdown()

    print("--- System Shutdown Complete ---")

if __name__ == "__main__":
    main()
