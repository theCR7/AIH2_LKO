"""Interactive pyvis network rendering for the Investigate screen (PRD F4.1).

Renders a case subgraph offline: ``Network(cdn_resources="in_line")`` +
``generate_html()`` so vis.js is inlined and no temp files are written
(CLAUDE.md rule #13). Node size = risk, colour = band, suspicious edges red.
Physics is disabled once stabilised so the graph does not drift during the demo.
"""

from __future__ import annotations

import streamlit as st
from pyvis.network import Network

from app.components.styles import TOKENS
from core.casegraph import CaseSubgraph, load_case_subgraph

_BAND_COLOR = {"high": TOKENS["risk_high"], "medium": TOKENS["risk_medium"],
               "low": TOKENS["risk_low"]}

# Injected so vis.js stops the simulation after it settles.
_STOP_PHYSICS = """
<script type="text/javascript">
  if (typeof network !== "undefined") {
    network.once("stabilizationIterationsDone", function () {
      network.setOptions({ physics: false });
    });
  }
</script>
"""


def render_case_graph_html(case_id: str, height: int = 550) -> str:
    """Return a self-contained HTML string for the case's interactive graph."""
    sub = load_case_subgraph(case_id)
    return _to_html(sub, height)


@st.cache_data(show_spinner=False)
def cached_case_graph_html(case_id: str, version: int, height: int = 550) -> str:
    """Cached wrapper over :func:`render_case_graph_html` (ITERATIONS P9 perf).

    Building the pyvis HTML (layout + inlined vis.js) is the heaviest per-rerun
    cost on the Investigate page. Keyed by ``case_id`` and the data ``version``
    token so it recomputes only after a new generate/detection run.
    """
    return render_case_graph_html(case_id, height)


def _to_html(sub: CaseSubgraph, height: int) -> str:
    net = Network(height=f"{height}px", width="100%", directed=True,
                  cdn_resources="in_line", bgcolor="#ffffff", font_color="#0f172a")
    net.set_options("""
    {
      "physics": {"stabilization": {"enabled": true, "iterations": 200},
                  "barnesHut": {"gravitationalConstant": -12000, "springLength": 140}},
      "interaction": {"hover": true, "tooltipDelay": 120},
      "edges": {"arrows": {"to": {"enabled": true, "scaleFactor": 0.6}}, "smooth": false}
    }
    """)
    for n in sub.nodes:
        net.add_node(n["id"], label=n["id"], color=_BAND_COLOR.get(n["band"], "#94A3B8"),
                     size=15 + n["risk"] / 3.0,
                     title=f"{n['id']} · {n['name']} ({n['bank']})<br>risk {n['risk']}")
    present = {n["id"] for n in sub.nodes}
    for e in sub.edges:
        if e["source"] not in present or e["target"] not in present:
            continue
        net.add_edge(e["source"], e["target"],
                     color=TOKENS["risk_high"] if e["suspicious"] else "#CBD5E1",
                     width=3 if e["suspicious"] else 1,
                     label=e["label"],
                     title=f"{e['txn_id']} · {e['label']} · {e['date']}")
    html = net.generate_html(notebook=False)
    return html.replace("</body>", _STOP_PHYSICS + "</body>")
