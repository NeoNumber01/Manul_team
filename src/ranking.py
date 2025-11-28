import pandas as pd
import networkx as nx


def compute_pagerank(G: nx.DiGraph) -> pd.DataFrame:
    """
    Compute PageRank values for all nodes in the graph.
    Returns a DataFrame with:
        stop_id, pagerank
    """
    pr = nx.pagerank(G, alpha=0.85)

    df_pr = pd.DataFrame({
        "stop_id": list(pr.keys()),
        "pagerank": list(pr.values())
    })

    return df_pr.set_index("stop_id")


def compute_pagerank_and_risk(G: nx.DiGraph, delay_df: pd.DataFrame) -> pd.DataFrame:
    """
    Combine PageRank with real-time delay data.

    delay_df must contain:
        stop_id, delay_minutes

    Output:
        stop_name, pagerank, delay, impact
    """

    # -----------------------------
    # 1. Compute PageRank
    # -----------------------------
    pr_df = compute_pagerank(G)

    # -----------------------------
    # 2. Prepare delays
    # -----------------------------
    delay_df = delay_df.copy()
    delay_df = delay_df.groupby("stop_id", as_index=True)["delay_minutes"].mean()

    # Ensure all stops have a delay value (0 if missing)
    delay_df = delay_df.reindex(pr_df.index).fillna(0)

    # -----------------------------
    # 3. Merge PageRank + delays
    # -----------------------------
    result = pr_df.copy()
    result["delay"] = delay_df
    result["impact"] = result["pagerank"] * result["delay"]

    # -----------------------------
    # 4. Add stop names from the graph
    # -----------------------------
    result["stop_name"] = result.index.map(lambda s: G.nodes[s].get("name", ""))

    # Sort by highest impact — most important for visualization
    result = result.sort_values("impact", ascending=False)

    return result
