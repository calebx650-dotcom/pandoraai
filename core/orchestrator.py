
import time
from enum import Enum, auto
from core.knowledge_graph import KnowledgeGraph
from core.questioning import QuestioningModule
from core.research import ResearchModule
from core.processing import ProcessingModule
from core.reasoning import ReasoningModule

class SystemState(Enum):
    IDLE = auto()
    GENERATING_QUESTIONS = auto()
    RESEARCHING = auto()
    PROCESSING = auto()
    INTEGRATING = auto()
    REASONING = auto()
    SHUTTING_DOWN = auto()

class Orchestrator:
    def __init__(self):
        self.state = SystemState.IDLE
        print(f"Orchestrator initialized in state: {self.state.name}")
        self.knowledge_graph = KnowledgeGraph()
        self.questioning_module = QuestioningModule(self.knowledge_graph)
        self.research_module = ResearchModule()
        self.processing_module = ProcessingModule()
        self.reasoning_module = ReasoningModule()
        self.running = False

    def start(self):
        print("Orchestrator starting the learning loop...")
        self.running = True
        while self.running:
            self.run_cycle()
            time.sleep(5) # Pause between cycles to be observable

    def run_cycle(self):
        print(f"\n--- New Learning Cycle --- State: {self.state.name} ---")

        if self.state == SystemState.IDLE:
            self.state = SystemState.GENERATING_QUESTIONS

        elif self.state == SystemState.GENERATING_QUESTIONS:
            question = self.questioning_module.generate_question()
            self.current_question = question
            self.state = SystemState.RESEARCHING

        elif self.state == SystemState.RESEARCHING:
            raw_data = self.research_module.research(self.current_question)
            self.current_data = raw_data
            self.state = SystemState.PROCESSING

        elif self.state == SystemState.PROCESSING:
            structured_knowledge = self.processing_module.process(self.current_data)
            self.current_knowledge = structured_knowledge
            self.state = SystemState.INTEGRATING

        elif self.state == SystemState.INTEGRATING:
            print(f"  -> [Integration] Integrating knowledge into the graph...")
            self.knowledge_graph.add_knowledge(self.current_knowledge)
            self.state = SystemState.REASONING

        elif self.state == SystemState.REASONING:
            self.reasoning_module.reason()
            self.state = SystemState.IDLE # Loop back to the beginning

    def shutdown(self):
        print("Orchestrator is shutting down...")
        self.running = False
        self.knowledge_graph.close()
        print("Orchestrator has shut down.")
