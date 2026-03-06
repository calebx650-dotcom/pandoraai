
class QuestioningModule:
    def __init__(self, knowledge_graph):
        self.knowledge_graph = knowledge_graph

    def generate_question(self):
        print("  -> [Questioning] Analyzing knowledge graph to generate a new question...")
        
        # Find a node with no outgoing relationships (a leaf node)
        target_concept = self.knowledge_graph.find_node_with_few_connections()

        if target_concept:
            question = f"What is the role of {target_concept} in science?"
            print(f"  -> [Questioning] Found an unexplored concept: '{target_concept}'. Asking a new question.")
        else:
            question = "What is the relationship between stress and strain in materials?"
            print("  -> [Questioning] No specific gaps found. Using a default question.")
        
        return question
