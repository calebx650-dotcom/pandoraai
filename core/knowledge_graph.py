
from neo4j import GraphDatabase
from neo4j import GraphDatabase
from config import config

class KnowledgeGraph:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
        )
        self.test_connection()

    def close(self):
        self.driver.close()

    def test_connection(self):
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 'Connection successful' AS message")
                print(result.single()["message"])
                return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def get_all_nodes_and_relationships(self):
        with self.driver.session() as session:
            return session.execute_read(self._get_all_data)

    def find_node_with_few_connections(self):
        with self.driver.session() as session:
            return session.execute_read(self._find_least_connected_node)

    def add_knowledge(self, structured_knowledge):
        nodes = structured_knowledge.get("nodes", [])
        edges = structured_knowledge.get("edges", [])
        with self.driver.session() as session:
            for node_label in nodes:
                session.execute_write(self._create_node, node_label)
            for edge_info in edges:
                start_node, relationship, end_node = edge_info
                session.execute_write(self._create_relationship, start_node, end_node, relationship)

    def _get_all_data(self, tx):
        query = "MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m"
        results = tx.run(query)
        return [(record["n"], record["r"], record["m"]) for record in results]

    def _find_least_connected_node(self, tx):
        query = (
            "MATCH (c:Concept) "
            "WHERE NOT (c)-->() "
            "RETURN c.label LIMIT 1"
        )
        result = tx.run(query)
        record = result.single()
        return record[0] if record else None

    def _create_node(self, tx, label):
        query = (
            "MERGE (n:Concept {label: $label}) "
            "RETURN n"
        )
        result = tx.run(query, label=label)
        print(f"    - Merged Node: {result.single()[0]['label']}")

    def _create_relationship(self, tx, start_label, end_label, relationship_type):
        query = (
            "MATCH (a:Concept {label: $start_label}) "
            "MATCH (b:Concept {label: $end_label}) "
            "MERGE (a)-[r:%s]->(b) "
            "RETURN type(r)"
        ) % relationship_type.upper()
        tx.run(query, start_label=start_label, end_label=end_label)
        print(f"    - Merged Relationship: {start_label} -> {relationship_type.upper()} -> {end_label}")
