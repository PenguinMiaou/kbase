"""Knowledge graph computation and management for KBase."""
import hashlib
import time
import numpy as np
from pathlib import Path
from kbase.config import load_settings


def _edge_id(src: str, tgt: str) -> str:
    """Deterministic edge ID from sorted file IDs (undirected by default)."""
    pair = sorted([src, tgt])
    return hashlib.md5(f"{pair[0]}:{pair[1]}".encode()).hexdigest()


def compute_graph(store, threshold: float = 0.65, max_edges_per_node: int = 8):
    """Compute document relationships using semantic similarity.

    Strategy:
    1. Get all document embeddings from ChromaDB (average of chunk embeddings)
    2. Compute pairwise cosine similarity
    3. Create edges for pairs above threshold
    4. Also add path-based relationships (same directory = weak link)

    Args:
        store: KBaseStore instance
        threshold: minimum cosine similarity to create an edge (0-1)
        max_edges_per_node: cap edges per document to reduce noise
    """
    conn = store.conn
    c = conn.cursor()

    # Get all indexed files
    c.execute("SELECT file_id, file_path, file_name, file_type, source_dir FROM files WHERE error IS NULL OR error = ''")
    files = [dict(row) for row in c.fetchall()]
    if len(files) < 2:
        return {"status": "skipped", "reason": "fewer than 2 files", "nodes": len(files), "edges": 0}

    file_map = {f["file_id"]: f for f in files}
    file_ids = list(file_map.keys())

    # Step 1: Compute document-level embeddings (average of chunk embeddings)
    doc_vectors = {}
    try:
        # Get all embeddings from ChromaDB in batches
        all_data = store.collection.get(include=["embeddings", "metadatas"])
        if all_data["embeddings"] is None or len(all_data["embeddings"]) == 0:
            return {"status": "skipped", "reason": "no embeddings found", "nodes": len(files), "edges": 0}

        # Group embeddings by file_id
        file_embeddings = {}
        embeddings_arr = np.array(all_data["embeddings"]) if not isinstance(all_data["embeddings"], np.ndarray) else all_data["embeddings"]
        for i, meta in enumerate(all_data["metadatas"]):
            fid = meta.get("file_id", "")
            is_parent = meta.get("is_parent")
            if is_parent and str(is_parent).lower() in ("true", "1"):
                continue
            if fid in file_map and i < len(embeddings_arr):
                if fid not in file_embeddings:
                    file_embeddings[fid] = []
                file_embeddings[fid].append(embeddings_arr[i])

        # Average embeddings per document
        for fid, embs in file_embeddings.items():
            arr = np.array(embs)
            avg = arr.mean(axis=0)
            norm = np.linalg.norm(avg)
            if norm > 0:
                doc_vectors[fid] = avg / norm  # L2 normalize
    except Exception as e:
        return {"status": "error", "reason": str(e), "nodes": len(files), "edges": 0}

    if len(doc_vectors) < 2:
        return {"status": "skipped", "reason": "fewer than 2 documents with embeddings", "nodes": len(files), "edges": 0}

    # Step 2: Compute pairwise cosine similarity (vectorized)
    vec_ids = list(doc_vectors.keys())
    matrix = np.array([doc_vectors[fid] for fid in vec_ids], dtype=np.float32)
    sim_matrix = np.clip(matrix @ matrix.T, -1.0, 1.0)  # clip to prevent floating point issues
    np.fill_diagonal(sim_matrix, 0)  # zero self-similarity

    # Step 3: Create edges — use numpy to find pairs above threshold efficiently
    now = time.time()
    new_edges = []
    edge_count_per_node = {}
    existing_eids = set()

    # Get upper triangle indices where similarity > threshold
    rows, cols = np.where((sim_matrix > threshold) & np.tri(len(vec_ids), dtype=bool, k=-1).T)
    scores = sim_matrix[rows, cols]
    # Sort by score descending
    order = np.argsort(-scores)

    for idx in order:
        i, j = int(rows[idx]), int(cols[idx])
        score = float(scores[idx])
        src_id, tgt_id = vec_ids[i], vec_ids[j]

        src_count = edge_count_per_node.get(src_id, 0)
        tgt_count = edge_count_per_node.get(tgt_id, 0)
        if src_count >= max_edges_per_node and tgt_count >= max_edges_per_node:
            continue

        eid = _edge_id(src_id, tgt_id)
        new_edges.append((eid, src_id, tgt_id, "auto", "", "none", round(score, 4), "semantic", now, now))
        existing_eids.add(eid)
        edge_count_per_node[src_id] = src_count + 1
        edge_count_per_node[tgt_id] = tgt_count + 1

    # Step 4: Add path-based relationships (same directory)
    dir_groups = {}
    for fid, info in file_map.items():
        parent = str(Path(info["file_path"]).parent)
        if parent:
            dir_groups.setdefault(parent, []).append(fid)

    for dir_path, group_ids in dir_groups.items():
        if len(group_ids) < 2 or len(group_ids) > 30:
            continue
        for i in range(len(group_ids)):
            for j in range(i + 1, len(group_ids)):
                eid = _edge_id(group_ids[i], group_ids[j])
                if eid not in existing_eids:
                    new_edges.append((eid, group_ids[i], group_ids[j], "auto", "", "none", 0.3, "path", now, now))
                    existing_eids.add(eid)

    # Step 5: Write to database (replace auto edges, keep manual ones)
    c.execute("DELETE FROM document_edges WHERE edge_type = 'auto'")
    if new_edges:
        c.executemany("""
            INSERT OR REPLACE INTO document_edges
            (edge_id, source_file_id, target_file_id, edge_type, label, direction, score, method, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, new_edges)
    conn.commit()

    return {
        "status": "completed",
        "nodes": len(files),
        "edges_computed": len(new_edges),
        "edges_semantic": sum(1 for e in new_edges if e[7] == "semantic"),
        "edges_path": sum(1 for e in new_edges if e[7] == "path"),
        "threshold": threshold,
    }


def get_graph_data(store, edge_types=None, min_score=0.0, file_type=None, source_dir=None):
    """Get full graph data (nodes + edges) for visualization.

    Returns:
        dict with 'nodes' and 'edges' arrays ready for Cytoscape.js
    """
    conn = store.conn
    c = conn.cursor()

    # Get nodes (files)
    query = "SELECT file_id, file_path, file_name, file_type, source_dir, chunk_count FROM files WHERE error IS NULL OR error = ''"
    params = []
    if file_type:
        query += " AND file_type = ?"
        ft = file_type if file_type.startswith('.') else '.' + file_type
        params.append(ft)
    if source_dir:
        query += " AND source_dir = ?"
        params.append(source_dir)
    c.execute(query, params)
    files = [dict(row) for row in c.fetchall()]
    file_set = {f["file_id"] for f in files}

    # Get edges
    edge_query = "SELECT * FROM document_edges WHERE score >= ?"
    edge_params = [min_score]
    if edge_types:
        placeholders = ",".join("?" * len(edge_types))
        edge_query += f" AND edge_type IN ({placeholders})"
        edge_params.extend(edge_types)
    c.execute(edge_query, edge_params)
    raw_edges = [dict(row) for row in c.fetchall()]

    # Filter edges to only include nodes in our set
    edges = [e for e in raw_edges if e["source_file_id"] in file_set and e["target_file_id"] in file_set]

    # Get saved positions
    c.execute("SELECT * FROM graph_node_positions")
    positions = {row["file_id"]: dict(row) for row in c.fetchall()}

    # Compute node degree (connection count)
    degree = {}
    for e in edges:
        degree[e["source_file_id"]] = degree.get(e["source_file_id"], 0) + 1
        degree[e["target_file_id"]] = degree.get(e["target_file_id"], 0) + 1

    # Build Cytoscape.js-compatible data
    nodes = []
    for f in files:
        fid = f["file_id"]
        pos = positions.get(fid, {})
        nodes.append({
            "data": {
                "id": fid,
                "label": f["file_name"],
                "file_path": f["file_path"],
                "file_type": f["file_type"] or "",
                "source_dir": f["source_dir"] or "",
                "chunk_count": f["chunk_count"] or 0,
                "degree": degree.get(fid, 0),
            },
            "position": {"x": pos.get("x", 0), "y": pos.get("y", 0)} if pos else None,
            "locked": bool(pos.get("pinned", 0)) if pos else False,
        })

    cy_edges = []
    for e in edges:
        cy_edges.append({
            "data": {
                "id": e["edge_id"],
                "source": e["source_file_id"],
                "target": e["target_file_id"],
                "edge_type": e["edge_type"],
                "label": e["label"] or "",
                "direction": e["direction"],
                "score": e["score"],
                "method": e["method"],
            }
        })

    return {"nodes": nodes, "edges": cy_edges}


def get_local_graph(store, file_id: str, depth: int = 2, min_score: float = 0.0):
    """Get subgraph centered on a specific file, up to N hops."""
    conn = store.conn
    c = conn.cursor()

    visited = set()
    frontier = {file_id}

    for _ in range(depth):
        if not frontier:
            break
        visited |= frontier
        new_frontier = set()
        for fid in frontier:
            c.execute("""
                SELECT source_file_id, target_file_id FROM document_edges
                WHERE (source_file_id = ? OR target_file_id = ?) AND score >= ?
            """, (fid, fid, min_score))
            for row in c.fetchall():
                neighbor = row["target_file_id"] if row["source_file_id"] == fid else row["source_file_id"]
                if neighbor not in visited:
                    new_frontier.add(neighbor)
        frontier = new_frontier
    visited |= frontier

    if not visited:
        return {"nodes": [], "edges": []}

    # Get node info
    placeholders = ",".join("?" * len(visited))
    c.execute(f"SELECT file_id, file_path, file_name, file_type, source_dir, chunk_count FROM files WHERE file_id IN ({placeholders})", list(visited))
    files = [dict(row) for row in c.fetchall()]

    # Get edges between visited nodes
    c.execute(f"""
        SELECT * FROM document_edges
        WHERE source_file_id IN ({placeholders}) AND target_file_id IN ({placeholders}) AND score >= ?
    """, list(visited) + list(visited) + [min_score])
    edges = [dict(row) for row in c.fetchall()]

    # Get positions
    c.execute(f"SELECT * FROM graph_node_positions WHERE file_id IN ({placeholders})", list(visited))
    positions = {row["file_id"]: dict(row) for row in c.fetchall()}

    degree = {}
    for e in edges:
        degree[e["source_file_id"]] = degree.get(e["source_file_id"], 0) + 1
        degree[e["target_file_id"]] = degree.get(e["target_file_id"], 0) + 1

    nodes = []
    for f in files:
        fid = f["file_id"]
        pos = positions.get(fid, {})
        nodes.append({
            "data": {
                "id": fid,
                "label": f["file_name"],
                "file_path": f["file_path"],
                "file_type": f["file_type"] or "",
                "source_dir": f["source_dir"] or "",
                "chunk_count": f["chunk_count"] or 0,
                "degree": degree.get(fid, 0),
                "is_center": fid == file_id,
            },
            "position": {"x": pos.get("x", 0), "y": pos.get("y", 0)} if pos else None,
            "locked": bool(pos.get("pinned", 0)) if pos else False,
        })

    cy_edges = []
    for e in edges:
        cy_edges.append({
            "data": {
                "id": e["edge_id"],
                "source": e["source_file_id"],
                "target": e["target_file_id"],
                "edge_type": e["edge_type"],
                "label": e["label"] or "",
                "direction": e["direction"],
                "score": e["score"],
                "method": e["method"],
            }
        })

    return {"nodes": nodes, "edges": cy_edges, "center": file_id}


def add_edge(store, source_id: str, target_id: str, edge_type: str = "confirmed",
             label: str = "", direction: str = "forward"):
    """Manually add or confirm an edge."""
    conn = store.conn
    c = conn.cursor()
    eid = _edge_id(source_id, target_id)
    now = time.time()

    # Check if edge exists
    c.execute("SELECT edge_id, edge_type FROM document_edges WHERE edge_id = ?", (eid,))
    existing = c.fetchone()

    if existing:
        # Upgrade auto -> confirmed/labeled
        c.execute("""
            UPDATE document_edges SET edge_type = ?, label = ?, direction = ?, updated_at = ?
            WHERE edge_id = ?
        """, (edge_type, label, direction, now, eid))
    else:
        c.execute("""
            INSERT INTO document_edges (edge_id, source_file_id, target_file_id, edge_type, label, direction, score, method, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (eid, source_id, target_id, edge_type, label, direction, 1.0, "manual", now, now))
    conn.commit()
    return {"edge_id": eid, "status": "created" if not existing else "updated"}


def update_edge(store, edge_id: str, edge_type: str = None, label: str = None, direction: str = None):
    """Update an existing edge."""
    conn = store.conn
    c = conn.cursor()
    updates = []
    params = []
    if edge_type is not None:
        updates.append("edge_type = ?")
        params.append(edge_type)
    if label is not None:
        updates.append("label = ?")
        params.append(label)
    if direction is not None:
        updates.append("direction = ?")
        params.append(direction)
    if not updates:
        return {"status": "no_changes"}
    updates.append("updated_at = ?")
    params.append(time.time())
    params.append(edge_id)
    c.execute(f"UPDATE document_edges SET {', '.join(updates)} WHERE edge_id = ?", params)
    conn.commit()
    return {"status": "updated", "rows": c.rowcount}


def delete_edge(store, edge_id: str):
    """Delete an edge."""
    conn = store.conn
    c = conn.cursor()
    c.execute("DELETE FROM document_edges WHERE edge_id = ?", (edge_id,))
    conn.commit()
    return {"status": "deleted", "rows": c.rowcount}


def save_positions(store, positions: list):
    """Save node positions for canvas/whiteboard mode.

    Args:
        positions: list of {"file_id": str, "x": float, "y": float, "pinned": bool}
    """
    conn = store.conn
    c = conn.cursor()
    now = time.time()
    for pos in positions:
        c.execute("""
            INSERT OR REPLACE INTO graph_node_positions (file_id, x, y, pinned, color_group, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (pos["file_id"], pos["x"], pos["y"], int(pos.get("pinned", 0)), pos.get("color_group", ""), now))
    conn.commit()
    return {"status": "saved", "count": len(positions)}


def get_graph_stats(store):
    """Get graph statistics."""
    conn = store.conn
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM files WHERE error IS NULL OR error = ''")
    node_count = c.fetchone()["cnt"]
    c.execute("SELECT edge_type, COUNT(*) as cnt FROM document_edges GROUP BY edge_type")
    edge_stats = {row["edge_type"]: row["cnt"] for row in c.fetchall()}
    c.execute("SELECT COUNT(*) as cnt FROM graph_node_positions WHERE pinned = 1")
    pinned = c.fetchone()["cnt"]
    c.execute("SELECT MAX(updated_at) as last_compute FROM document_edges WHERE edge_type = 'auto'")
    row = c.fetchone()
    last_compute = row["last_compute"] if row else None
    return {
        "nodes": node_count,
        "edges_total": sum(edge_stats.values()),
        "edges_auto": edge_stats.get("auto", 0),
        "edges_confirmed": edge_stats.get("confirmed", 0),
        "edges_labeled": edge_stats.get("labeled", 0),
        "pinned_nodes": pinned,
        "last_compute": last_compute,
    }


def boost_search_with_graph(store, results: list, query_file_id: str = None) -> list:
    """Phase 3: Boost search results using confirmed graph relationships.

    If a search result's document has confirmed/labeled edges to other high-scoring
    results, boost its score slightly (graph coherence bonus).
    """
    if not results or len(results) < 2:
        return results

    conn = store.conn
    c = conn.cursor()

    # Get file_ids from results
    result_file_ids = set()
    for r in results:
        fid = r.get("metadata", {}).get("file_id", "")
        if fid:
            result_file_ids.add(fid)

    if len(result_file_ids) < 2:
        return results

    # Get confirmed/labeled edges between result files
    placeholders = ",".join("?" * len(result_file_ids))
    c.execute(f"""
        SELECT source_file_id, target_file_id, score FROM document_edges
        WHERE edge_type IN ('confirmed', 'labeled')
        AND source_file_id IN ({placeholders})
        AND target_file_id IN ({placeholders})
    """, list(result_file_ids) + list(result_file_ids))

    # Build adjacency set
    connected = set()
    for row in c.fetchall():
        connected.add(row["source_file_id"])
        connected.add(row["target_file_id"])

    # Boost results that are in the connected set
    GRAPH_BOOST = 0.05
    for r in results:
        fid = r.get("metadata", {}).get("file_id", "")
        if fid in connected:
            r["score"] = r.get("score", 0) + GRAPH_BOOST
            r["graph_boosted"] = True

    # Re-sort by score
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results
