# 🌸 Chiikawa Rail: Intelligent Railway Knowledge Graph & Routing System

An advanced decision-support system that transforms raw transit data into a semantic **Knowledge Graph** to analyze network robustness and provide reliable routing recommendations.

## 🚀 Key Features
- **Semantic Data Modeling:** Built a Knowledge Graph using **RDFLib** and **SPARQL**, allowing for complex relationship querying beyond traditional SQL.
- **Graph Intelligence:** Implemented **PageRank** algorithms to identify critical network hubs and assess station "Risk Levels."
- **Robust Routing:** A custom routing engine that balances travel time with network reliability (Speed vs. Robustness).
- **3D Interactive Visualization:** Real-time geospatial dashboard powered by **PyDeck** and **Streamlit** to visualize cascading delay effects.

## 🛠️ Technical Stack
- **Backend:** Python (OOP), RDFLib (Knowledge Graphs), NetworkX (Graph Theory)
- **Frontend:** Streamlit, PyDeck (3D Geo-Spatial), Plotly
- **Data:** GTFS (Static & Real-time), REST APIs
- **Software Engineering:** Modular design, Type Hinting, Data Caching mechanisms

## 🧠 Core Logic: Why Knowledge Graphs?
Unlike standard tables, the RDF-based Knowledge Graph allows the system to understand the **context** of a station. By querying the graph with SPARQL, we can instantly identify how a delay at a "Hub" station impacts connecting local lines, enabling "Decision Intelligence" for passenger rerouting.

## 📸 Preview
![WhatsApp 图像2025-11-27于23 47 10_ae2c3255](https://github.com/user-attachments/assets/dc19d440-9a74-434d-bf16-29816a1ac579)

![WhatsApp 图像2025-11-27于23 46 58_63c7a3ac](https://github.com/user-attachments/assets/f73bd702-9b8a-4c4e-9a28-8526b9dc2e5e)

<img width="3154" height="1585" alt="image" src="https://github.com/user-attachments/assets/ebe9ae68-afd4-40a6-819a-fac819c0c713" />


---
