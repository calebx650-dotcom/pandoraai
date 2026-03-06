
import streamlit as st
import streamlit.components.v1 as components
import sys
import os
from pyvis.network import Network

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.knowledge_graph import KnowledgeGraph

st.set_page_config(layout="wide")
st.title("AI Research System - Knowledge Graph Visualizer")

# Fetch data from Neo4j
@st.cache_data
def get_graph_data():
    kg = KnowledgeGraph()
    data = kg.get_all_nodes_and_relationships()
    kg.close()
    return data

# Create the pyvis network
net = Network(height="750px", width="100%", bgcolor="#222222", font_color="white", notebook=True, cdn_resources='in_line')

# Get the data
graph_data = get_graph_data()

if graph_data:
    for n, r, m in graph_data:
        if n:
            net.add_node(n.id, label=n['label'])
        if m:
            net.add_node(m.id, label=m['label'])
        if r:
            net.add_edge(r.start_node.id, r.end_node.id, title=type(r).__name__)

    # Generate the HTML file
    try:
        path = './pyvis_graph.html'
        net.save_graph(path)
        HtmlFile = open(path, 'r', encoding='utf-8')
        components.html(HtmlFile.read(), height=800)
    except Exception as e:
        st.error(f"Failed to generate graph: {e}")
else:
    st.warning("The Knowledge Graph is currently empty. Run the main AI system to populate it.")
