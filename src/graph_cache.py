import pickle
import networkx as nx


def save_graph_cache(G: nx.DiGraph, path: str):
    """
    Save a NetworkX graph to a pickle file.
    Speeds up future runs by avoiding rebuilding the graph every time.
    """
    with open(path, "wb") as f:
        pickle.dump(G, f)


def load_graph_cache(path: str):
    """
    Load a cached graph from a pickle file.
    Returns None if the file does not exist or fails to load.
    """
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None
