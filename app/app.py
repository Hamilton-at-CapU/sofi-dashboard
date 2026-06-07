from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from shiny import reactive, req
from shiny.express import input, render, ui
from shinywidgets import render_plotly


def load_remuneration_data(path: str | Path | None = None) -> pd.DataFrame:
    """Load remuneration_2024.json into a flat DataFrame."""
    if path is None:
        here = Path(__file__).parent
        path = here / "remuneration_2024.json"

    with open(path) as f:
        records = json.load(f)

    rows = []
    for record in records:
        year = record["year"]
        municipality = record["municipality"]
        for person in record["councillors"]:
            rows.append({
                "year":         year,
                "municipality": municipality,
                "name":         person["name"],
                "position":     person["position"],
                "remuneration": person["remuneration"],
                "expenses":     person["expenses"],
            })
    return pd.DataFrame(rows)


plot_df = load_remuneration_data()

MUNICIPALITIES = sorted(plot_df["municipality"].unique().tolist())
DEFAULT_MUNIS   = ["Burnaby", "Coquitlam", "Richmond"]
YEAR            = int(plot_df["year"].max())
mayor_df        = plot_df[plot_df["position"] == "Mayor"].copy()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

ui.page_opts(title="SOFI Remuneration Dashboard", fillable=False)

with ui.sidebar():
    ui.h6("Selected Municipalities")
    ui.input_selectize(
        "municipalities",
        None,
        choices=MUNICIPALITIES,
        selected=DEFAULT_MUNIS,
        multiple=True,
        width="100%",
    )
    ui.hr()
    ui.markdown("Compare mayor and councillor remuneration across BC municipalities.")


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

with ui.navset_tab():

    with ui.nav_panel("Comparative Distribution"):
        with ui.card(full_screen=True, style="height:calc(100vh - 160px)"):
            with ui.card_header(class_="d-flex align-items-center gap-2 flex-wrap"):
                ui.span(f"Distribution of Mayor Remuneration ({YEAR})")
                ui.span(" | ")

                @render.ui
                def density_avg_boxes():
                    munis = input.municipalities()
                    all_vals  = mayor_df["remuneration"].dropna()
                    sel_vals  = mayor_df[mayor_df["municipality"].isin(munis)]["remuneration"].dropna()

                    def fmt(val):
                        return f"${val:,.0f}" if not pd.isna(val) else "N/A"

                    all_avg = all_vals.mean() if not all_vals.empty else float("nan")
                    sel_avg = sel_vals.mean() if not sel_vals.empty else float("nan")

                    return ui.TagList(
                        ui.tags.span(
                            ui.tags.small("All municipalities avg: ", style="opacity:.7;"),
                            ui.tags.strong(fmt(all_avg)),
                            class_="badge text-bg-secondary me-1 fw-normal fs-6 px-2 py-1",
                        ),
                        ui.tags.span(
                            ui.tags.small("Selected avg: ", style="opacity:.7;"),
                            ui.tags.strong(fmt(sel_avg)),
                            class_="badge text-bg-primary fw-normal fs-6 px-2 py-1",
                        ),
                    )

            ui.card_footer("Density distribution includes all municipalities with available data.")

            @render_plotly
            def density_chart():
                munis = req(input.municipalities())

                all_d = mayor_df[["municipality", "remuneration"]].dropna()
                if all_d.empty:
                    return go.Figure()

                values = all_d["remuneration"].values

                # KDE via Silverman's rule
                x_min, x_max = values.min(), values.max()
                x_range = np.linspace(x_min, x_max, 300)
                bw = 1.06 * values.std() * len(values) ** -0.2
                kde_y = np.array([
                    np.mean(np.exp(-0.5 * ((x - values) / bw) ** 2) / (bw * np.sqrt(2 * np.pi)))
                    for x in x_range
                ])

                fig = make_subplots(
                    rows=2, cols=1,
                    row_heights=[0.85, 0.15],
                    shared_xaxes=True,
                    vertical_spacing=0.02,
                )

                # KDE curve
                fig.add_trace(go.Scatter(
                    x=x_range,
                    y=kde_y,
                    mode="lines",
                    fill="tozeroy",
                    line=dict(color="rgba(99,110,250,0.8)", width=2),
                    fillcolor="rgba(99,110,250,0.15)",
                    name="All municipalities",
                    hoverinfo="skip",
                ), row=1, col=1)

                colors = px.colors.qualitative.D3
                selected_rows = all_d[all_d["municipality"].isin(munis)]

                # Vertical lines + annotations for selected municipalities
                for i, (_, row) in enumerate(selected_rows.iterrows()):
                    muni = row["municipality"]
                    val  = row["remuneration"]
                    pct  = (values < val).mean() * 100
                    color = colors[i % len(colors)]

                    fig.add_vline(
                        x=val,
                        line=dict(color=color, width=2, dash="dash"),
                        row=1, col=1,
                    )
                    fig.add_annotation(
                        x=val,
                        y=kde_y.max(),
                        text=f"{muni}<br>(${val:,.0f}, {pct:.0f}th pct)",
                        showarrow=True,
                        arrowhead=2,
                        arrowcolor=color,
                        font=dict(size=11, color=color),
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor=color,
                        ax=0,
                        ay=-36,
                        xref="x", yref="y",
                    )

                # Rug — all municipalities in grey
                fig.add_trace(go.Scatter(
                    x=all_d["remuneration"],
                    y=np.zeros(len(all_d)),
                    mode="markers",
                    marker=dict(
                        symbol="line-ns",
                        size=12,
                        color="rgba(150,150,150,0.4)",
                        line=dict(color="rgba(150,150,150,0.4)", width=1),
                    ),
                    text=all_d["municipality"],
                    hovertemplate="%{text}: $%{x:,.0f}<extra></extra>",
                    name="All municipalities",
                    showlegend=False,
                ), row=2, col=1)

                # Rug — selected municipalities highlighted
                for i, (_, row) in enumerate(selected_rows.iterrows()):
                    muni  = row["municipality"]
                    val   = row["remuneration"]
                    color = colors[i % len(colors)]

                    fig.add_trace(go.Scatter(
                        x=[val],
                        y=[0],
                        mode="markers",
                        marker=dict(
                            symbol="line-ns",
                            size=16,
                            color=color,
                            line=dict(color=color, width=2),
                        ),
                        name=muni,
                        hovertemplate=f"{muni}: ${val:,.0f}<extra></extra>",
                        showlegend=False,
                    ), row=2, col=1)

                fig.update_layout(
                    xaxis2_title=f"Mayor Remuneration ({YEAR})",
                    yaxis_title="Density",
                    showlegend=False,
                    margin=dict(l=10, r=10, t=10, b=10),
                )
                fig.update_yaxes(visible=False, row=2, col=1)
                fig.update_xaxes(tickformat="$,.0f", row=1, col=1)
                fig.update_xaxes(tickformat="$,.0f", showticklabels=True, row=2, col=1)

                return fig
