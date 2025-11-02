from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx
import plotly.graph_objects as go
import streamlit as st

# ── Tunables / constants ─────────────────────────────────────────────────────────
MAX_PROP_SCAN_DEPTH = 3  # used when scanning nested structures for goal lists

# ── Page & Sidebar ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="GoalWeaver — Live Goal Graph", layout="wide")

default_state = os.getenv("GOALWEAVER_STATE", "state.json")
state_path = st.sidebar.text_input("State file", value=default_state, help="Path to JSON state")
st.sidebar.caption(str(Path(state_path).resolve()))

status_choices = ["PENDING", "READY", "IN_PROGRESS", "DONE", "FAILED"]
status_filter = st.sidebar.multiselect("Statuses", status_choices, default=status_choices)

layout_choice = st.sidebar.selectbox(
    "Graph layout",
    ["spring", "kamada_kawai", "circular", "shell", "random"],
    index=0,
    help="Choose a NetworkX layout",
)
seed = st.sidebar.number_input("Layout seed", min_value=0, max_value=9999, value=42, step=1)
show_titles = st.sidebar.checkbox("Show titles on nodes (instead of numbers)", value=False)
show_state_head = st.sidebar.checkbox("Show first 30 lines of state.json (debug)", value=False)

if st.sidebar.button("Refresh now"):
    st.rerun()


# ── Helpers ───────────────────────────────────────────────────────────────────────
def load_state(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"goals": [], "logs": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_status(s: Any) -> str:
    """
    Normalize varied labels to one of: PENDING, READY, IN_PROGRESS, DONE, FAILED.
    Accepts booleans or custom strings like 'success', 'complete', 'error', 'blocked', etc.
    """
    if isinstance(s, bool):
        return "DONE" if s else "FAILED"
    s = (str(s or "PENDING")).strip().replace("-", "_").replace(" ", "_").upper()
    synonyms = {
        "SUCCESS": "DONE",
        "SUCCEEDED": "DONE",
        "COMPLETE": "DONE",
        "COMPLETED": "DONE",
        "OK": "DONE",
        "PASS": "DONE",
        "ERROR": "FAILED",
        "FAIL": "FAILED",
        "FAILED": "FAILED",
        "BROKEN": "FAILED",
        "STALLED": "PENDING",
        "BLOCKED": "PENDING",
        "WAITING": "PENDING",
        "QUEUED": "READY",
        "READY": "READY",
        "RUNNING": "IN_PROGRESS",
        "WORKING": "IN_PROGRESS",
        "INPROGRESS": "IN_PROGRESS",
        "IN_PROGRESS": "IN_PROGRESS",
        "PENDING": "PENDING",
    }
    return synonyms.get(
        s, s if s in {"PENDING", "READY", "IN_PROGRESS", "DONE", "FAILED"} else "PENDING"
    )


def _first_n_lines(path: str, n: int = 30) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return "".join([next(f) for _ in range(n)])
    except Exception:
        return ""


def _candidate_goals_lists(state: Any) -> list[list[dict[str, Any]]]:
    """
    Find lists of goal-like dicts in a flexible way:
    - state['goals']
    - state['graph']['goals']
    - state['nodes']
    - any nested list that looks like [{'id' or 'uid' ...}, ...]
    """
    out: list[list[dict[str, Any]]] = []

    def looks_like_goals_list(x: Any) -> bool:
        if not (isinstance(x, list) and x and isinstance(x[0], dict)):
            return False
        d0 = x[0]
        return any(k in d0 for k in ("id", "uid", "uuid", "goal_id"))

    # obvious places
    if isinstance(state, dict):
        if isinstance(state.get("goals"), list):
            out.append(state["goals"])
        if isinstance(state.get("graph"), dict) and isinstance(state["graph"].get("goals"), list):
            out.append(state["graph"]["goals"])
        if isinstance(state.get("nodes"), list):
            out.append(state["nodes"])

    # recursive scan up to shallow depth
    def walk(a: Any, depth: int = 0):
        if depth > MAX_PROP_SCAN_DEPTH:
            return
        if looks_like_goals_list(a):
            out.append(a)  # type: ignore[arg-type]
            return
        if isinstance(a, dict):
            for v in a.values():
                walk(v, depth + 1)
        elif isinstance(a, list):
            for v in a:
                walk(v, depth + 1)

    walk(state)
    # de-duplicate by id list memory address (best-effort)
    seen = set()
    uniq: list[list[dict[str, Any]]] = []
    for lst in out:
        key = id(lst)
        if key not in seen:
            seen.add(key)
            uniq.append(lst)
    return uniq


def extract_goals(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized goals list; if not found, fall back to logs-derived nodes."""
    lists = _candidate_goals_lists(state)
    goals: list[dict[str, Any]] = []
    for raw in lists:
        for g in raw:
            gid = g.get("id") or g.get("uid") or g.get("uuid") or g.get("goal_id")
            if not gid:
                continue
            deps = (
                g.get("dependencies")
                or g.get("deps")
                or g.get("parents")
                or g.get("requires")
                or []
            )
            status = g.get("status") or g.get("state") or g.get("goal_status")
            # If only 'success' flag is available, map it
            if status is None and "success" in g:
                status = bool(g.get("success"))
            goals.append(
                {
                    "id": gid,
                    "title": g.get("title")
                    or g.get("name")
                    or g.get("desc")
                    or g.get("description")
                    or f"Goal {len(goals) + 1}",
                    "status": normalize_status(status),
                    "dependencies": deps,
                }
            )
        if goals:
            break  # use the first plausible list

    if goals:
        return goals

    # Fallback: build nodes from logs if present
    logs = state.get("logs") or []
    ids = []
    for row in logs:
        gid = row.get("goal")
        if gid:
            ids.append(gid)
    ids = list(dict.fromkeys(ids))
    return [
        {"id": gid, "title": f"Goal {i+1}", "status": "PENDING", "dependencies": []}
        for i, gid in enumerate(ids)
    ]


def build_graph(
    goals: list[dict[str, Any]], keep_status: list[str]
) -> tuple[nx.DiGraph, dict[str, int]]:
    keep = {normalize_status(s) for s in keep_status}
    G = nx.DiGraph()
    idx_of: dict[str, int] = {}

    # Nodes (filter by normalized status)
    for i, g in enumerate(goals, start=1):
        status = normalize_status(g.get("status"))
        if status not in keep:
            continue
        gid = g["id"]
        idx_of[gid] = i
        G.add_node(gid, idx=i, title=g.get("title", f"Goal {i}"), status=status)

    # Edges (only if both ends present)
    for g in goals:
        gid = g["id"]
        if gid not in G:
            continue
        for dep in g.get("dependencies") or []:
            if dep in G and not G.has_edge(dep, gid):
                G.add_edge(dep, gid)  # dependency -> goal
    return G, idx_of


def status_color(s: str) -> str:
    s = normalize_status(s)
    return {
        "DONE": "#22c55e",  # green-500
        "FAILED": "#ef4444",  # red-500
        "IN_PROGRESS": "#f59e0b",  # amber-500
        "READY": "#60a5fa",  # blue-400
        "PENDING": "#94a3b8",  # slate-400
    }.get(s, "#94a3b8")


def compute_layout(G: nx.Graph, layout: str, seed_val: int) -> dict[str, tuple[float, float]]:
    """Return a single-layout result; avoid many early returns (ruff PLR0911)."""
    if G.number_of_nodes() == 0:
        return {}

    layout_key = (layout or "spring").lower()
    if layout_key == "spring":
        pos_raw = nx.spring_layout(G, seed=seed_val, k=0.8)
    elif layout_key == "kamada_kawai":
        pos_raw = nx.kamada_kawai_layout(G)
    elif layout_key == "circular":
        pos_raw = nx.circular_layout(G)
    elif layout_key == "shell":
        pos_raw = nx.shell_layout(G)
    elif layout_key == "random":
        pos_raw = nx.random_layout(G, seed=seed_val)
    else:
        pos_raw = nx.spring_layout(G, seed=seed_val)

    # normalize to floats and explicit tuples
    return {str(n): (float(xy[0]), float(xy[1])) for n, xy in pos_raw.items()}


def fig_from_graph(
    G: nx.DiGraph, pos: dict[str, tuple[float, float]], show_titles: bool
) -> go.Figure:
    # Edges as a single line trace separated by None
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=1.4, color="rgba(100,116,139,0.6)"),
        hoverinfo="none",
        showlegend=False,
    )

    # Nodes with labels + hover tooltips
    node_x, node_y, node_text, node_color, node_hover = [], [], [], [], []
    for n, data in G.nodes(data=True):
        x, y = pos[n]
        node_x.append(x)
        node_y.append(y)
        label = data.get("title") if show_titles else str(data.get("idx"))
        node_text.append(label)
        node_color.append(status_color(data.get("status")))
        node_hover.append(
            f"{data.get('idx')}. {data.get('title','')} — {data.get('status','PENDING')}"
        )

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="middle center",
        hovertext=node_hover,
        hoverinfo="text",
        marker=dict(size=18, color=node_color, line=dict(width=1, color="#0b1220")),
        textfont=dict(color="#e5e7eb"),
        showlegend=False,
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        dragmode="pan",
    )
    fig.update_xaxes(scaleanchor="y", scaleratio=1)  # keep aspect ratio
    return fig


# ── Body ──────────────────────────────────────────────────────────────────────────
st.title("🧭 GoalWeaver — Live Goal Graph")

state = load_state(state_path)
logs = state.get("logs", [])
all_goals = extract_goals(state)

# Sidebar quick debug
st.sidebar.markdown(f"**Loaded goals:** {len(all_goals)}  \n**Logs:** {len(logs)}")
if all_goals:
    dist = Counter([normalize_status(g.get("status")) for g in all_goals])
    st.sidebar.markdown(
        "**Status distribution:**  \n" + "  \n".join(f"- {k}: {v}" for k, v in dist.items())
    )
if show_state_head:
    st.sidebar.code(_first_n_lines(state_path), language="json")

# Logs table (deprecation-safe: new width API with fallback)
st.subheader("Logs")
try:
    st.dataframe(logs, width="stretch", hide_index=True)  # new Streamlit API
except TypeError:
    st.dataframe(logs, use_container_width=True, hide_index=True)  # old Streamlit fallback

# Graph
st.subheader("Graph")
G, _ = build_graph(all_goals, status_filter)

if G.number_of_nodes() == 0:
    st.warning(
        "No goals match the current status filter **or** the state file has no goals.\n"
        "Try selecting more statuses in the sidebar and confirm the state file path."
    )
else:
    pos = compute_layout(G, layout_choice, seed)
    fig = fig_from_graph(G, pos, show_titles=show_titles)
    st.plotly_chart(fig, config={"displayModeBar": True, "scrollZoom": True, "responsive": True})

st.caption(
    "**Legend:** ✅ DONE, ❌ FAILED, 🟡 IN_PROGRESS, 🔵 READY, ⚪ PENDING  \n"
    "Edges point from *dependency* → *goal*. Use the sidebar to filter and change layouts."
)
