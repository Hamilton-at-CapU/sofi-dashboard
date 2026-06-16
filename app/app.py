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


def load_remuneration_data(path=None):
    if path is None:
        path = Path(__file__).parent / "remuneration_2024.json"
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
                "benefits":     person.get("benefits"),
            })
    return pd.DataFrame(rows)


# Load both years
_plot_df_2024 = load_remuneration_data(Path(__file__).parent / "remuneration_2024.json")
_plot_df_2023 = load_remuneration_data(Path(__file__).parent / "remuneration_2023.json")
_muni_data_2024 = pd.DataFrame(json.load(open(Path(__file__).parent / "municipal_data_2024.json")))
_muni_data_2023 = pd.DataFrame(json.load(open(Path(__file__).parent / "municipal_data_2023.json")))

ALL_DATA = {
    2024: (_plot_df_2024, _muni_data_2024),
    2023: (_plot_df_2023, _muni_data_2023),
}

# Use 2024 for sidebar filters and municipality list
plot_df = _plot_df_2024
MUNICIPALITIES  = sorted(plot_df["municipality"].unique().tolist())
DEFAULT_MUNIS   = ["Burnaby", "North Vancouver (District)", "Pitt Meadows", "Powell River", "Squamish"]

_muni_data = _muni_data_2024
_pop = (
    _muni_data[["municipality", "Population"]]
    .dropna()
    .set_index("municipality")["Population"]
    .astype(int)
)
_ptax = (
    _muni_data[["municipality", "Total Property Taxes and Charges on Typical House"]]
    .dropna()
    .set_index("municipality")["Total Property Taxes and Charges on Typical House"]
    .astype(int)
)

POP_MIN  = 5000
POP_MAX  = 500_000
PTAX_MIN = int(_ptax.min() // 500     * 500)
PTAX_MAX = int((_ptax.max() + 499)    // 500     * 500)

TRENDS_CHOICES = {
    "pop":   "Mayor Remuneration vs Population",
    "ptax":  "Mayor Remuneration vs Property Tax on Typical House",
    "taxes": "Mayor Remuneration vs Total Taxes Collected",
}

VIEW_CHOICES = {
    "mayor":       "Mayor Remuneration",
    "council":     "Councillor Remuneration",
    "ratio":       "Councillor / Mayor Ratio",
    "mayor_exp":   "Mayor Expenses",
    "council_exp": "Councillor Expenses",
    "mayor_ben":   "Mayor Benefits",
    "council_ben": "Councillor Benefits",
}


def _derive(plot_df, muni_data):
    """Derive all plot dataframes from a given year's data."""
    mayor_df = plot_df[plot_df["position"] == "Mayor"].copy()

    councillor_avg_df = (
        plot_df[plot_df["position"] != "Mayor"]
        .groupby("municipality", as_index=False)["remuneration"]
        .mean()
    )
    councillor_to_mayor_df = (
        councillor_avg_df
        .rename(columns={"remuneration": "avg_councillor"})
        .merge(
            mayor_df[["municipality", "remuneration"]].rename(
                columns={"remuneration": "mayor_remuneration"}
            ),
            on="municipality", how="inner",
        )
        .assign(ratio=lambda d: d["avg_councillor"] / d["mayor_remuneration"] * 100)
        .dropna(subset=["ratio"])
    )
    mayor_expenses_df         = mayor_df[["municipality", "expenses"]].dropna().copy()
    councillor_avg_expenses_df = (
        plot_df[plot_df["position"] != "Mayor"]
        .groupby("municipality", as_index=False)["expenses"].mean()
    )
    mayor_benefits_df = mayor_df[["municipality", "benefits"]].dropna(subset=["benefits"]).copy()
    councillor_avg_benefits_df = (
        plot_df[plot_df["position"] != "Mayor"]
        .groupby("municipality", as_index=False)["benefits"].mean()
        .dropna(subset=["benefits"])
    )
    scatter_df = (
        mayor_df[["municipality", "remuneration"]]
        .merge(muni_data[["municipality", "Population"]].dropna(), on="municipality", how="inner")
        .rename(columns={"remuneration": "mayor_remuneration"})
        .dropna()
    )
    scatter_ptax_df = (
        mayor_df[["municipality", "remuneration"]]
        .merge(muni_data[["municipality", "Total Property Taxes and Charges on Typical House"]].dropna(), on="municipality", how="inner")
        .rename(columns={"remuneration": "mayor_remuneration", "Total Property Taxes and Charges on Typical House": "ptax"})
        .dropna()
    )
    scatter_taxes_df = (
        mayor_df[["municipality", "remuneration"]]
        .merge(muni_data[["municipality", "Total Taxes Collected"]].dropna(), on="municipality", how="inner")
        .rename(columns={"remuneration": "mayor_remuneration", "Total Taxes Collected": "total_taxes"})
        .dropna()
    )
    return {
        "mayor_df":                  mayor_df,
        "councillor_avg_df":         councillor_avg_df,
        "councillor_to_mayor_df":    councillor_to_mayor_df,
        "mayor_expenses_df":         mayor_expenses_df,
        "councillor_avg_expenses_df":councillor_avg_expenses_df,
        "mayor_benefits_df":         mayor_benefits_df,
        "councillor_avg_benefits_df":councillor_avg_benefits_df,
        "scatter_df":                scatter_df,
        "scatter_ptax_df":           scatter_ptax_df,
        "scatter_taxes_df":          scatter_taxes_df,
    }


_derived = {yr: _derive(*data) for yr, data in ALL_DATA.items()}

# Pre-compute mayor YoY % change 2023 -> 2024
_mayors_2023 = _derived[2023]["mayor_df"][["municipality", "remuneration"]].rename(columns={"remuneration": "rem_2023"})
_mayors_2024 = _derived[2024]["mayor_df"][["municipality", "remuneration"]].rename(columns={"remuneration": "rem_2024"})
_yoy_df = (
    _mayors_2023.merge(_mayors_2024, on="municipality", how="inner")
    .assign(pct_change=lambda d: (d["rem_2024"] - d["rem_2023"]) / d["rem_2023"] * 100)
    .dropna(subset=["pct_change"])
)

# Pre-compute average councillor YoY % change 2023 -> 2024
_council_2023 = _derived[2023]["councillor_avg_df"][["municipality", "remuneration"]].rename(columns={"remuneration": "rem_2023"})
_council_2024 = _derived[2024]["councillor_avg_df"][["municipality", "remuneration"]].rename(columns={"remuneration": "rem_2024"})
_councillor_yoy_df = (
    _council_2023.merge(_council_2024, on="municipality", how="inner")
    .assign(pct_change=lambda d: (d["rem_2024"] - d["rem_2023"]) / d["rem_2023"] * 100)
    .dropna(subset=["pct_change"])
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kde(values, n=300):
    x_range = np.linspace(values.min(), values.max(), n)
    bw = 1.06 * values.std() * len(values) ** -0.2
    kde_y = np.array([
        np.mean(np.exp(-0.5 * ((x - values) / bw) ** 2) / (bw * np.sqrt(2 * np.pi)))
        for x in x_range
    ])
    return x_range, kde_y


def _build_fig(data, col, munis, x_title, tick_fmt, tick_suffix, label_fn):
    values = data[col].values
    x_range, kde_y = _kde(values)

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.85, 0.15],
        shared_xaxes=True,
        vertical_spacing=0.02,
    )

    fig.add_trace(go.Scatter(
        x=x_range, y=kde_y,
        mode="lines", fill="tozeroy",
        line=dict(color="rgba(99,110,250,0.8)", width=2),
        fillcolor="rgba(99,110,250,0.15)",
        name="All municipalities", hoverinfo="skip",
    ), row=1, col=1)

    colors = px.colors.qualitative.D3
    selected_rows = data[data["municipality"].isin(munis)]

    for i, (_, row) in enumerate(selected_rows.iterrows()):
        muni  = row["municipality"]
        val   = row[col]
        pct   = (values < val).mean() * 100
        color = colors[i % len(colors)]
        fig.add_vline(x=val, line=dict(color=color, width=2, dash="dash"), row=1, col=1)
        fig.add_annotation(
            x=val, y=kde_y.max(),
            text=f"{muni}<br>({label_fn(val, pct)})",
            showarrow=True, arrowhead=2, arrowcolor=color,
            font=dict(size=11, color=color),
            bgcolor="rgba(255,255,255,0.8)", bordercolor=color,
            ax=0, ay=-36, xref="x", yref="y",
        )

    hover_all = [
        f"{m}: {label_fn(v, (values < v).mean() * 100)}"
        for m, v in zip(data["municipality"], data[col])
    ]
    fig.add_trace(go.Scatter(
        x=data[col], y=np.zeros(len(data)),
        mode="markers",
        marker=dict(symbol="line-ns", size=12,
                    color="rgba(150,150,150,0.4)",
                    line=dict(color="rgba(150,150,150,0.4)", width=1)),
        text=hover_all,
        hovertemplate="%{text}<extra></extra>",
        showlegend=False,
    ), row=2, col=1)

    for i, (_, row) in enumerate(selected_rows.iterrows()):
        muni  = row["municipality"]
        val   = row[col]
        pct   = (values < val).mean() * 100
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=[val], y=[0], mode="markers",
            marker=dict(symbol="line-ns", size=16, color=color,
                        line=dict(color=color, width=2)),
            text=[f"{muni}: {label_fn(val, pct)}"],
            hovertemplate="%{text}<extra></extra>",
            showlegend=False,
        ), row=2, col=1)

    fig.update_layout(
        xaxis2_title=x_title,
        yaxis_title="Density",
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    fig.update_yaxes(visible=False, row=2, col=1)
    fig.update_xaxes(tickformat=tick_fmt, ticksuffix=tick_suffix, row=1, col=1)
    fig.update_xaxes(
        tickformat=tick_fmt, ticksuffix=tick_suffix,
        showticklabels=True, row=2, col=1,
    )
    return fig


def _build_scatter(data, x_col, munis, x_title, x_fmt, x_suffix="", year=2024):
    colors     = px.colors.qualitative.D3
    selected   = data[data["municipality"].isin(munis)]
    unselected = data[~data["municipality"].isin(munis)]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=unselected[x_col],
        y=unselected["mayor_remuneration"],
        mode="markers",
        marker=dict(color="rgba(150,150,150,0.4)", size=8),
        text=unselected["municipality"],
        hovertemplate=f"%{{text}}<br>{x_title}: %{{x:{x_fmt}}}{x_suffix}<br>Mayor: $%{{y:,.0f}}<extra></extra>",
        showlegend=False,
    ))

    for i, (_, row) in enumerate(selected.iterrows()):
        color = colors[i % len(colors)]
        x_val = row[x_col]
        y_val = row["mayor_remuneration"]
        muni  = row["municipality"]
        if x_suffix == "%":
            x_str = f"{x_val:{x_fmt}}{x_suffix}"
        elif x_fmt in ("$,.0f", ",.0f"):
            x_str = f"${x_val:,.0f}"
        else:
            x_str = f"{x_val:,}"
        fig.add_trace(go.Scatter(
            x=[x_val],
            y=[y_val],
            mode="markers+text",
            marker=dict(color=color, size=11, line=dict(color="white", width=1)),
            text=[muni], textposition="top center",
            textfont=dict(color=color, size=11),
            hovertemplate=f"{muni}<br>{x_title}: {x_str}<br>Mayor: ${y_val:,.0f}<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=f"Mayor Remuneration ({year})",
        margin=dict(l=10, r=10, t=10, b=10),
    )
    fig.update_xaxes(tickformat=x_fmt, ticksuffix=x_suffix)
    fig.update_yaxes(tickformat="$,.0f")
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

ui.page_opts(title="Council Pay Dashboard", fillable=False)

with ui.sidebar():

    ui.markdown("Compare mayor and councillor remuneration across BC municipalities with populations greater than 5,000 people.")
    ui.hr()

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
    ui.markdown("Filter municipalities by Population, Property Tax, or select manually above.")
    ui.input_radio_buttons(
        "filter_type",
        "",
        choices={
            "none": "Manual Selection",
            "pop":  "Population",
            "ptax": "Property Tax on Typical House",
        },
        selected="none",
    )
    with ui.panel_conditional("input.filter_type === 'pop'"):
        ui.input_slider(
            "pop_range",
            None,
            min=POP_MIN,
            max=POP_MAX,
            value=[5_000, 50_000],
            step=5000,
            sep=",",
            width="100%",
        )
    with ui.panel_conditional("input.filter_type === 'ptax'"):
        ui.input_slider(
            "ptax_range",
            None,
            min=PTAX_MIN,
            max=PTAX_MAX,
            value=[3_000, 5_000],
            step=500,
            pre="$",
            sep=",",
            width="100%",
        )
    ui.hr(),
    ui.markdown(
        "Data extracted from remuneration schedules in SOFI reports.  [View remuneration schedules](https://raw.githubusercontent.com/Hamilton-at-CapU/sofi-dashboard/main/app/remuneration_schedules_2024.pdf)"
        ),
    ui.markdown(
        "Dashboard by Andrew Hamilton, [Computing & Data Science at Capilano University](https://www.capilanou.ca/programs--courses/search--select/explore-our-areas-of-study/arts--sciences/school-of-science-technology-engineering--mathematics-stem/computing--data-science-department/).  "
    ),
    ui.markdown(
        "Contact via [Linkedin](https://www.linkedin.com/in/andrew-hamilton-phd/) or [email](mailto:andrew@bcmunicipaldata.org).  "
    ),
    ui.markdown(
        "Source code available at [Hamilton-at-CapU on GitHub](https://github.com/Hamilton-at-CapU/sofi-dashboard).  "
    ),


# ---------------------------------------------------------------------------
# Reactive filter sync
# ---------------------------------------------------------------------------

@reactive.effect
def _sync_muni_filter():
    filter_type = input.filter_type()
    if filter_type == "pop":
        lo, hi = input.pop_range()
        in_range = _pop[(_pop >= lo) & (_pop <= hi)].index.tolist()
    elif filter_type == "ptax":
        lo, hi = input.ptax_range()
        in_range = _ptax[(_ptax >= lo) & (_ptax <= hi)].index.tolist()
    else:
        return
    ui.update_selectize("municipalities", selected=sorted(in_range))


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

with ui.navset_tab():

    # ── Distribution tab ────────────────────────────────────────────────────
    with ui.nav_panel("Distributions"):
        with ui.card(full_screen=True, style="height:calc(100vh - 200px)"):

            with ui.card_header(class_="d-flex align-items-center gap-2 flex-wrap"):

                ui.input_select(
                    "view",
                    None,
                    choices=VIEW_CHOICES,
                    selected="mayor",
                )

                ui.input_select(
                    "dist_year",
                    None,
                    choices={"2024": "2024", "2023": "2023"},
                    selected="2024",
                )

                @render.ui
                def card_header_content():
                    view  = input.view()
                    munis = input.municipalities()
                    year  = int(input.dist_year())
                    d     = _derived[year]

                    if view == "mayor":
                        sel_vals = d["mayor_df"][d["mayor_df"]["municipality"].isin(munis)]["remuneration"].dropna()
                        title    = f"Distribution of Mayor Remuneration ({year})"
                        def fmt_val(v): return f"${v:,.0f}"
                    elif view == "council":
                        sel_vals = d["councillor_avg_df"][d["councillor_avg_df"]["municipality"].isin(munis)]["remuneration"].dropna()
                        title    = f"Distribution of Average Councillor Remuneration by Municipality ({year})"
                        def fmt_val(v): return f"${v:,.0f}"
                    elif view == "ratio":
                        sel_vals = d["councillor_to_mayor_df"][d["councillor_to_mayor_df"]["municipality"].isin(munis)]["ratio"].dropna()
                        title    = f"Average Councillor Remuneration as % of Mayor Remuneration ({year})"
                        def fmt_val(v): return f"{v:.1f}%"
                    elif view == "mayor_exp":
                        sel_vals = d["mayor_expenses_df"][d["mayor_expenses_df"]["municipality"].isin(munis)]["expenses"].dropna()
                        title    = f"Distribution of Mayor Expenses ({year})"
                        def fmt_val(v): return f"${v:,.0f}"
                    elif view == "council_exp":
                        sel_vals = d["councillor_avg_expenses_df"][d["councillor_avg_expenses_df"]["municipality"].isin(munis)]["expenses"].dropna()
                        title    = f"Distribution of Average Councillor Expenses by Municipality ({year})"
                        def fmt_val(v): return f"${v:,.0f}"
                    elif view == "mayor_ben":
                        sel_vals = d["mayor_benefits_df"][d["mayor_benefits_df"]["municipality"].isin(munis)]["benefits"].dropna()
                        title    = f"Distribution of Mayor Benefits ({year})"
                        def fmt_val(v): return f"${v:,.0f}"
                    else:
                        sel_vals = d["councillor_avg_benefits_df"][d["councillor_avg_benefits_df"]["municipality"].isin(munis)]["benefits"].dropna()
                        title    = f"Distribution of Average Councillor Benefits by Municipality ({year})"
                        def fmt_val(v): return f"${v:,.0f}"

                    sel_avg = sel_vals.mean() if not sel_vals.empty else float("nan")
                    def badge_val(v):
                        return fmt_val(v) if not pd.isna(v) else "N/A"

                    return ui.TagList(
                        ui.span(title),
                        ui.span(" | "),
                        ui.tags.span(
                            ui.tags.small("Avg of Selected: ", style="opacity:.7;"),
                            ui.tags.strong(badge_val(sel_avg)),
                            class_="badge text-bg-primary fw-normal fs-6 px-2 py-1",
                        ),
                    )

            @render.ui
            def card_footer_content():
                footers = {
                    "mayor":       "Density distribution includes all municipalities with available data.",
                    "council":     "Each point represents the average remuneration across all councillors (excluding mayor) for that municipality.",
                    "ratio":       "Each point is a municipality's mean councillor pay divided by its mayor's pay, expressed as a percentage.",
                    "mayor_exp":   "Density distribution of mayor expenses across all municipalities with available data.",
                    "council_exp": "Each point represents the average expenses across all councillors (excluding mayor) for that municipality.",
                    "mayor_ben":   "Density distribution of mayor benefits across municipalities with available data. Not all municipalities provide benefits.",
                    "council_ben": "Each point represents the average benefits across all councillors (excluding mayor) for that municipality. Not all municipalities provide benefits.",
                }
                return ui.card_footer(footers[input.view()])

            @render_plotly
            def main_chart():
                view  = req(input.view())
                munis = req(input.municipalities())
                year  = int(input.dist_year())
                d     = _derived[year]

                if view == "mayor":
                    data = d["mayor_df"][["municipality", "remuneration"]].dropna()
                    return _build_fig(data, "remuneration", munis, x_title=f"Mayor Remuneration ({year})", tick_fmt="$,.0f", tick_suffix="", label_fn=lambda v, p: f"${v:,.0f}, {p:.0f}th pct")
                elif view == "council":
                    data = d["councillor_avg_df"].dropna(subset=["remuneration"])
                    return _build_fig(data, "remuneration", munis, x_title=f"Average Councillor Remuneration ({year})", tick_fmt="$,.0f", tick_suffix="", label_fn=lambda v, p: f"${v:,.0f}, {p:.0f}th pct")
                elif view == "ratio":
                    data = d["councillor_to_mayor_df"].dropna(subset=["ratio"])
                    return _build_fig(data, "ratio", munis, x_title=f"Avg Councillor Remuneration as % of Mayor ({year})", tick_fmt=".1f", tick_suffix="%", label_fn=lambda v, p: f"{v:.1f}%, {p:.0f}th pct")
                elif view == "mayor_exp":
                    data = d["mayor_expenses_df"].dropna(subset=["expenses"])
                    return _build_fig(data, "expenses", munis, x_title=f"Mayor Expenses ({year})", tick_fmt="$,.0f", tick_suffix="", label_fn=lambda v, p: f"${v:,.0f}, {p:.0f}th pct")
                elif view == "council_exp":
                    data = d["councillor_avg_expenses_df"].dropna(subset=["expenses"])
                    return _build_fig(data, "expenses", munis, x_title=f"Average Councillor Expenses ({year})", tick_fmt="$,.0f", tick_suffix="", label_fn=lambda v, p: f"${v:,.0f}, {p:.0f}th pct")
                elif view == "mayor_ben":
                    data = d["mayor_benefits_df"].dropna(subset=["benefits"])
                    return _build_fig(data, "benefits", munis, x_title=f"Mayor Benefits ({year})", tick_fmt="$,.0f", tick_suffix="", label_fn=lambda v, p: f"${v:,.0f}, {p:.0f}th pct")
                else:
                    data = d["councillor_avg_benefits_df"].dropna(subset=["benefits"])
                    return _build_fig(data, "benefits", munis, x_title=f"Average Councillor Benefits ({year})", tick_fmt="$,.0f", tick_suffix="", label_fn=lambda v, p: f"${v:,.0f}, {p:.0f}th pct")

    # ── Trends tab ──────────────────────────────────────────────────────────
    with ui.nav_panel("Trends"):
        with ui.card(full_screen=True, style="height:calc(100vh - 200px)"):

            with ui.card_header(class_="d-flex align-items-center gap-2 flex-wrap"):
                ui.input_select(
                    "trends_view",
                    None,
                    choices=TRENDS_CHOICES,
                    selected="pop",
                )

                ui.input_select(
                    "trends_year",
                    None,
                    choices={"2024": "2024", "2023": "2023"},
                    selected="2024",
                )

                @render.ui
                def trends_header_content():
                    return ui.span(f"({input.trends_year()})")

            @render.ui
            def trends_footer_content():
                return ui.card_footer(
                    "Each point is a municipality. Selected municipalities are highlighted and labelled."
                )

            @render_plotly
            def trends_chart():
                munis = req(input.municipalities())
                tview = req(input.trends_view())
                year  = int(input.trends_year())
                d     = _derived[year]

                if tview == "pop":
                    return _build_scatter(d["scatter_df"], "Population", munis,
                                          x_title=f"Population ({year})", x_fmt=",", year=year)
                elif tview == "ptax":
                    return _build_scatter(d["scatter_ptax_df"], "ptax", munis,
                                          x_title=f"Property Tax on Typical House ({year})", x_fmt="$,.0f", year=year)
                else:
                    return _build_scatter(d["scatter_taxes_df"], "total_taxes", munis,
                                          x_title=f"Total Taxes Collected ({year})", x_fmt="$,.0f", year=year)

    # ── Year Over Year tab ──────────────────────────────────────────────────────────
    with ui.nav_panel("Year Over Year"):
        with ui.card(full_screen=True, style="height:calc(100vh - 200px)"):

            with ui.card_header(class_="d-flex align-items-center gap-2 flex-wrap"):

                ui.input_select(
                    "yoy_view",
                    None,
                    choices={"mayor": "Mayor Remuneration", "council": "Avg Councillor Remuneration"},
                    selected="mayor",
                )

                @render.ui
                def yoy_header_content():
                    munis    = input.municipalities()
                    rview    = input.yoy_view()
                    data     = _yoy_df if rview == "mayor" else _councillor_yoy_df
                    sel_vals = data[data["municipality"].isin(munis)]["pct_change"].dropna()
                    sel_avg  = sel_vals.mean() if not sel_vals.empty else float("nan")
                    badge    = f"{sel_avg:.1f}%" if not pd.isna(sel_avg) else "N/A"
                    label    = "Mayor" if rview == "mayor" else "Avg Councillor"
                    return ui.TagList(
                        ui.span(f"{label} Remuneration % Change 2023 → 2024"),
                        ui.span(" | "),
                        ui.tags.span(
                            ui.tags.small("Avg of Selected: ", style="opacity:.7;"),
                            ui.tags.strong(badge),
                            class_="badge text-bg-primary fw-normal fs-6 px-2 py-1",
                        ),
                    )

            ui.card_footer("Each point is a municipality. Positive values indicate an increase from 2023 to 2024.")

            @render_plotly
            def yoy_chart():
                munis = req(input.municipalities())
                rview = req(input.yoy_view())
                data  = _yoy_df if rview == "mayor" else _councillor_yoy_df
                label = "Mayor" if rview == "mayor" else "Avg Councillor"
                return _build_fig(
                    data,
                    "pct_change",
                    munis,
                    x_title=f"{label} Remuneration % Change (2023 → 2024)",
                    tick_fmt=".1f",
                    tick_suffix="%",
                    label_fn=lambda v, p: f"{v:.1f}%, {p:.0f}th pct",
                )
