"""Interactive pyvis network for the Investigate screen (PRD F4.1).

Offline-safe: ``Network(cdn_resources="in_line")`` + ``generate_html()`` so vis.js
is inlined and no files are written (CLAUDE.md rule #13). Case nodes are shown at
full opacity, 1-hop neighbours dimmed. Node colour = risk band, shape = entity
type, size = connections; edge width = amount, red = suspicious. Colours follow
the active theme so light and dark both look right.
"""

from __future__ import annotations

import streamlit as st
from pyvis.network import Network

from app.components.theme import active_mode, tokens

_SHAPE = {"individual": "dot", "business": "square", "merchant": "square",
          "payroll": "diamond"}

_STOP_PHYSICS = """
<script type="text/javascript">
  if (typeof network !== "undefined") {
    network.once("stabilizationIterationsDone", function () {
      network.setOptions({ physics: false });
    });
  }
</script>
"""


@st.cache_data(show_spinner=False)
def cached_case_graph_html(case_id: str, version: int, hops: int, mode: str,
                           height: int = 520) -> tuple[str, bool]:
    """Cached graph HTML + capped flag. Keyed by case, data version, hops and theme."""
    from core.casegraph import load_case_subgraph
    sub = load_case_subgraph(case_id, hops=hops)
    return _to_html(sub, height), sub.capped


def _to_html(sub, height: int) -> str:
    t = tokens()
    dark = active_mode() == "dark"
    net = Network(height=f"{height}px", width="100%", directed=True,
                  cdn_resources="in_line", bgcolor=t["bg"], font_color=t["text"])
    net.set_options("""
    {
      "physics": {"stabilization": {"enabled": true, "iterations": 200},
                  "barnesHut": {"gravitationalConstant": -14000, "springLength": 150}},
      "interaction": {"hover": true, "tooltipDelay": 120, "navigationButtons": false},
      "edges": {"arrows": {"to": {"enabled": true, "scaleFactor": 0.5}}, "smooth": false}
    }
    """)

    degree: dict[str, int] = {}
    for e in sub.edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    present = {n["id"] for n in sub.nodes}
    for n in sub.nodes:
        is_case = n.get("is_case", True)
        color = t[f"risk_{n['band']}"] if is_case else t["text_muted"]
        size = 12 + min(degree.get(n["id"], 0), 10) * 2.5
        tip = (f"{n['id']} · {n['name']} ({n['bank']})<br>risk {n['risk']} · "
               f"{degree.get(n['id'], 0)} connections")
        net.add_node(n["id"], label=n["id"], shape=_SHAPE.get(n["type"], "dot"),
                     color={"background": color, "border": color},
                     opacity=1.0 if is_case else 0.35, size=size, title=tip,
                     font={"color": t["text"], "size": 12})

    for e in sub.edges:
        if e["source"] not in present or e["target"] not in present:
            continue
        susp = e["suspicious"]
        net.add_edge(
            e["source"], e["target"],
            color=t["risk_high"] if susp else (t["border"] if not dark else "#3A4150"),
            width=3 if susp else 1, label=e["label"] if susp else "",
            font={"color": t["text_muted"], "size": 10, "strokeWidth": 0},
            title=f"{e['txn_id']} · {e['label']} · {e['date']}")

    html = net.generate_html(notebook=False)
    return html.replace("</body>", _STOP_PHYSICS + "</body>")
