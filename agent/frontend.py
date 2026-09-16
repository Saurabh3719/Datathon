"""
Streamlit UI for the local Text-to-SQL agent. Maps the API's structured
fields onto specific UI affordances:
  - collapsible_suggested_answer -> a <details>/<summary>-style st.expander
    (its `title` is the collapsed label, `answer_summary` the body)
  - index_space_followups        -> a sidebar "index" list of buttons
  - llm_context_extraction / er_relationship_mapping -> shown together in
    a second, technical-detail expander alongside the raw SQL and, when the
    answer came from the OpenRouter fallback rather than a local template,
    an ASCII E-R diagram and the "source" badge
  - visualization + rows         -> a Plotly chart

Run (from repo root, with agent/app.py already running on :8000):
    python3 -m streamlit run agent/frontend.py
"""
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

API_URL = "http://localhost:8000/ask"

st.set_page_config(page_title="UPI Fraud Analytics -- Ask the Data", page_icon="💳", layout="wide")
st.title("💳 UPI Fraud & Merchant Risk Analytics -- Ask the Data")
st.caption(
    "Local, vetted SQL templates answer known question shapes with zero API cost or network call. "
    "Anything else falls back to a real OpenRouter API call (requires OPENROUTER_API_KEY) -- watch the "
    "'answered by' badge below each answer to see which path handled it."
)

if "last_response" not in st.session_state:
    st.session_state["last_response"] = None

with st.sidebar:
    st.subheader("Example questions")
    try:
        examples = requests.get("http://localhost:8000/examples", timeout=5).json()["examples"]
        for ex in examples:
            if st.button(ex, use_container_width=True, key=f"ex_{ex}"):
                st.session_state["question"] = ex
    except requests.RequestException:
        st.warning("Agent API not reachable at :8000 -- start it with:\n\n`python3 -m uvicorn agent.app:app --port 8000`")

    # index_space_followups render lower in the sidebar (a second `with
    # st.sidebar:` block below, after the answer is fetched) -- rendering
    # them here instead would show last run's answer's followups, since
    # session_state set later in the same script run isn't visible to
    # widgets already rendered earlier in that same run.
    followup_slot = st.container()

question = st.text_input("Ask a question about the data", key="question", placeholder="e.g. Which merchant has the highest chargeback count?")

if st.button("Ask", type="primary") or question:
    if not question.strip():
        st.info("Type a question above, or pick one from the sidebar.")
    else:
        try:
            resp = requests.post(API_URL, json={"question": question}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            st.error(f"Couldn't reach the agent API: {e}")
            st.stop()

        st.session_state["last_response"] = data

        if data.get("index_space_followups"):
            with followup_slot:
                st.divider()
                st.subheader("Follow-up index")
                for i, fq in enumerate(data["index_space_followups"]):
                    if st.button(fq, use_container_width=True, key=f"followup_{i}_{fq}"):
                        st.session_state["question"] = fq

        ctx = data["llm_context_extraction"]
        conf = ctx["confidence_score"]
        badge = "🟢" if conf >= 0.9 else ("🟡" if conf >= 0.5 else "🔴")
        source_badge = f"✨ OpenRouter ({ctx['model']})" if ctx.get("source") == "openrouter" else "📋 local template"
        st.caption(
            f"{badge} intent: `{ctx['intent']}` · confidence: {conf:.0%} · "
            f"keywords matched: {', '.join(ctx['keywords_matched']) or '—'} · answered by: {source_badge}"
        )

        # collapsible_suggested_answer as a <details>/<summary> block -- the
        # answer itself is collapsed behind the title until clicked.
        collapsible = data["collapsible_suggested_answer"]
        with st.expander(collapsible["title"], expanded=True):
            st.markdown(f"**{collapsible['answer_summary']}**")

        er = data.get("er_relationship_mapping")
        with st.expander("SQL & E-R mapping", expanded=False):
            if data.get("sql_query"):
                st.code(data["sql_query"], language="sql")
            if er:
                if er.get("kpis_calculated"):
                    st.markdown(f"**KPIs calculated:** {', '.join(er['kpis_calculated'])}")
                st.markdown(f"**Primary table:** `{er['primary_table']}`")
                if er["joined_tables"]:
                    st.markdown(f"**Joined tables:** {', '.join(f'`{t}`' for t in er['joined_tables'])}")
                if er["join_conditions"]:
                    st.markdown("**Join conditions:**")
                    for jc in er["join_conditions"]:
                        st.code(jc, language="sql")
                if er["variables_fetched"]:
                    st.markdown(f"**Variables fetched:** {', '.join(f'`{v}`' for v in er['variables_fetched'])}")
                if er.get("er_diagram_ascii"):
                    st.markdown("**E-R diagram:**")
                    st.code(er["er_diagram_ascii"], language="text")
            else:
                st.caption("No E-R mapping -- this question didn't resolve to a specific query template.")

        rows = data.get("rows") or []
        viz = data.get("visualization")
        if rows and viz:
            df = pd.DataFrame(rows)
            chart_type = viz["type"]
            x = viz.get("x_axis")
            y_spec = (viz.get("y_axis") or "").split(", ")
            y_cols = [c.strip() for c in y_spec if c.strip() in df.columns] or [c for c in df.columns if c != x]

            try:
                if chart_type == "line" and x in df.columns:
                    fig = px.line(df, x=x, y=y_cols, title=viz["title"])
                    st.plotly_chart(fig, use_container_width=True)
                elif chart_type == "bar" and x in df.columns:
                    fig = px.bar(df, x=x, y=y_cols[0], title=viz["title"])
                    st.plotly_chart(fig, use_container_width=True)
                elif chart_type == "pie" and x in df.columns:
                    fig = px.pie(df, names=x, values=y_cols[0], title=viz["title"])
                    st.plotly_chart(fig, use_container_width=True)
                elif chart_type == "metric_card":
                    st.metric(viz["title"], df.iloc[0][y_cols[0]])
                else:
                    st.dataframe(df, use_container_width=True)
            except Exception:
                st.dataframe(df, use_container_width=True)

            with st.expander(f"Raw result ({len(rows)} rows)", expanded=(viz["type"] == "table")):
                st.dataframe(df, use_container_width=True)
        elif rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

        if data.get("index_space_followups"):
            st.caption("See the sidebar's Follow-up index for related questions.")
