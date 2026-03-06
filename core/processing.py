
import spacy

class ProcessingModule:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
            print("  -> [Processing] spaCy model 'en_core_web_sm' loaded successfully.")
        except OSError:
            print("  -> [Processing] spaCy model not found. Please run: python -m spacy download en_core_web_sm")
            self.nlp = None

    def process(self, raw_data):
        print("  -> [Processing] Analyzing text with NLP model to extract concepts...")
        if not self.nlp or not raw_data:
            return {"nodes": [], "edges": []}

        # We'll just process the first document for now
        text = raw_data[0]
        doc = self.nlp(text)

        # Extract named entities as nodes
        nodes = list(set([ent.text for ent in doc.ents if ent.label_ in ["ORG", "PERSON", "WORK_OF_ART", "PRODUCT", "EVENT", "LAW"]]))
        print(f"  -> [Processing] Found {len(nodes)} potential concepts: {nodes[:5]}...")

        # For now, we'll create a simple placeholder relationship
        edges = []
        if len(nodes) > 1:
            edges.append((nodes[0], "RELATED_TO", nodes[1]))

        return {"nodes": nodes, "edges": edges}
