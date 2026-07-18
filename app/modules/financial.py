from __future__ import annotations

import plotly.graph_objects as go
from nicegui import ui

from app.core.db import get_session
from app.core.finance import summarize
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.property_service import PropertyService

# Neon cyberpunk chart palette (cyan / magenta / lime / amber)
_CHART = {
    "pi": "#00E5FF",
    "tax": "#FF2BD6",
    "ins": "#B8FF3C",
    "hoa": "#FFC107",
    "pmi": "#FF6B9D",
    "balance": "#00E5FF",
    "principal": "#00E5FF",
    "interest": "#FF2BD6",
    "paper": "#12151A",
    "plot": "#0B0D10",
    "grid": "rgba(0, 229, 255, 0.12)",
    "text": "#E8EDF4",
    "muted": "#8B96A8",
}


def _money(n: float) -> str:
    return f"${n:,.0f}"


def _money_exact(n: float) -> str:
    return f"${n:,.2f}"


def _chart_layout(**kwargs) -> dict:
    base = dict(
        paper_bgcolor=_CHART["paper"],
        plot_bgcolor=_CHART["plot"],
        font=dict(color=_CHART["text"], size=12, family="system-ui, sans-serif"),
        margin=dict(t=48, b=40, l=56, r=24),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=_CHART["muted"]),
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1C222C",
            bordercolor="#00E5FF",
            font=dict(color=_CHART["text"]),
        ),
    )
    base.update(kwargs)
    return base


def _axis_style(**extra) -> dict:
    style = dict(
        color=_CHART["muted"],
        gridcolor=_CHART["grid"],
        zeroline=False,
        linecolor=_CHART["grid"],
        tickfont=dict(color=_CHART["muted"]),
        title_font=dict(color=_CHART["muted"]),
    )
    style.update(extra)
    return style


def _summary_card(label: str, value: str, *, accent: bool = False) -> None:
    classes = "hb-metric px-4 py-3"
    if accent:
        classes += " hb-metric--accent"
    with ui.column().classes(classes).style("min-width: 9.5rem"):
        ui.label(label).classes("text-caption opacity-70")
        ui.label(value).classes("text-h5 text-weight-medium" if accent else "text-h6")


def _section(title: str):
    col = ui.column().classes("gap-2 flex-grow").style("min-width: 14rem; max-width: 22rem")
    with col:
        ui.label(title).classes("text-subtitle2 text-grey-6 text-weight-medium")
    return col


def render(prop: Property, container: ui.element) -> None:
    with get_session() as session:
        service = PropertyService(session)
        fresh = service.get_property(prop.id)
        assert fresh is not None
        fin = service.ensure_financial(fresh)
        list_price = float(getattr(fin, "list_price", None) or fin.purchase_price or 0)
        offer_price = float(getattr(fin, "offer_price", None) or 0)
        values = {
            "list_price": list_price,
            "offer_price": offer_price,
            "down_payment_pct": fin.down_payment_pct,
            "interest_rate_pct": fin.interest_rate_pct,
            "loan_term_years": fin.loan_term_years,
            "annual_property_tax": fin.annual_property_tax,
            "annual_insurance": fin.annual_insurance,
            "monthly_hoa": fin.monthly_hoa,
            "closing_cost_pct": fin.closing_cost_pct,
        }

    with container:
        ui.label("Financials").classes("text-h6")
        ui.label("Offer vs list, financing, and monthly housing cost.").classes(
            "text-caption text-grey-7"
        )

        hero = ui.row().classes("w-full gap-3 q-mt-md flex-wrap items-stretch")
        breakdown = ui.row().classes("w-full gap-3 q-mt-sm flex-wrap")

        with ui.row().classes("w-full gap-6 flex-wrap q-mt-lg items-start"):
            with _section("Purchase"):
                list_in = ui.number("List price", value=values["list_price"], format="%.0f").props(
                    "prefix=$ dense outlined"
                ).classes("w-full")
                offer_in = ui.number("Offer price", value=values["offer_price"], format="%.0f").props(
                    "prefix=$ dense outlined"
                ).classes("w-full")
                ui.label("Mortgage uses offer; leave offer blank to use list.").classes(
                    "text-caption text-grey-6"
                )

            with _section("Loan"):
                down = ui.number("Down payment", value=values["down_payment_pct"], format="%.1f").props(
                    "suffix=% dense outlined"
                ).classes("w-full")
                rate = ui.number("Interest rate", value=values["interest_rate_pct"], format="%.3f").props(
                    "suffix=% dense outlined"
                ).classes("w-full")
                term = ui.number("Term", value=values["loan_term_years"], format="%.0f").props(
                    "suffix=years dense outlined"
                ).classes("w-full")
                closing = ui.number(
                    "Closing costs", value=values["closing_cost_pct"], format="%.1f"
                ).props("suffix=% dense outlined").classes("w-full")

            with _section("Ownership costs"):
                tax = ui.number(
                    "Property tax / year", value=values["annual_property_tax"], format="%.0f"
                ).props("prefix=$ dense outlined").classes("w-full")
                insurance = ui.number(
                    "Insurance / year", value=values["annual_insurance"], format="%.0f"
                ).props("prefix=$ dense outlined").classes("w-full")
                hoa = ui.number("HOA / month", value=values["monthly_hoa"], format="%.0f").props(
                    "prefix=$ dense outlined"
                ).classes("w-full")

        charts = ui.column().classes("w-full q-mt-lg gap-2")

        def collect() -> dict:
            offer_val = float(offer_in.value or 0)
            list_val = float(list_in.value or 0)
            return {
                "list_price": list_val,
                "offer_price": offer_val,
                "down_payment_pct": float(down.value or 0),
                "interest_rate_pct": float(rate.value or 0),
                "loan_term_years": int(term.value or 30),
                "annual_property_tax": float(tax.value or 0),
                "annual_insurance": float(insurance.value or 0),
                "monthly_hoa": float(hoa.value or 0),
                "closing_cost_pct": float(closing.value or 0),
            }

        def redraw() -> None:
            data = collect()
            result = summarize(**data)

            hero.clear()
            with hero:
                _summary_card("Monthly payment", _money_exact(result.monthly_total), accent=True)
                _summary_card("Cash to close", _money(result.cash_to_close))
                _summary_card("Loan amount", _money(result.loan_amount))
                delta = result.offer_price - result.list_price if result.offer_price else 0
                if result.list_price and result.offer_price:
                    vs = f"{_money(abs(delta))} {'under' if delta < 0 else 'over'} list"
                    _summary_card("Offer vs list", vs if delta != 0 else "At list")
                else:
                    _summary_card("Price basis", _money(result.effective_price))

            breakdown.clear()
            with breakdown:
                parts = [
                    ("P&I", result.monthly_principal_interest),
                    ("Tax", result.monthly_tax),
                    ("Insurance", result.monthly_insurance),
                    ("HOA", result.monthly_hoa),
                ]
                if result.monthly_pmi > 0:
                    parts.append(("PMI", result.monthly_pmi))
                for label, val in parts:
                    with ui.column().classes("hb-metric px-3 py-2").style("min-width: 6.5rem"):
                        ui.label(label).classes("text-caption text-grey-6")
                        ui.label(_money_exact(val)).classes("text-body1 text-weight-medium")

            charts.clear()
            with charts:
                pie_labels = ["Principal & Interest", "Taxes", "Insurance", "HOA"]
                pie_values = [
                    result.monthly_principal_interest,
                    result.monthly_tax,
                    result.monthly_insurance,
                    result.monthly_hoa,
                ]
                pie_colors = [_CHART["pi"], _CHART["tax"], _CHART["ins"], _CHART["hoa"]]
                if result.monthly_pmi > 0:
                    pie_labels.append("PMI")
                    pie_values.append(result.monthly_pmi)
                    pie_colors.append(_CHART["pmi"])

                # Drop zero slices so the mix stays readable
                filtered = [
                    (lab, val, col)
                    for lab, val, col in zip(pie_labels, pie_values, pie_colors)
                    if val > 0
                ]
                if filtered:
                    pie = go.Figure(
                        data=[
                            go.Pie(
                                labels=[f[0] for f in filtered],
                                values=[f[1] for f in filtered],
                                hole=0.55,
                                marker=dict(
                                    colors=[f[2] for f in filtered],
                                    line=dict(color=_CHART["paper"], width=2),
                                ),
                                textinfo="label+percent",
                                textposition="outside",
                                textfont=dict(color=_CHART["text"]),
                                hovertemplate="%{label}: $%{value:,.0f}<extra></extra>",
                            )
                        ]
                    )
                    pie.update_layout(
                        **_chart_layout(
                            title=dict(
                                text="Monthly payment mix",
                                x=0,
                                xanchor="left",
                                font=dict(color=_CHART["text"]),
                            ),
                            showlegend=False,
                            height=340,
                            margin=dict(t=48, b=24, l=24, r=24),
                            annotations=[
                                dict(
                                    text=_money(result.monthly_total),
                                    x=0.5,
                                    y=0.5,
                                    font=dict(size=18, color="#00E5FF"),
                                    showarrow=False,
                                )
                            ],
                        )
                    )
                    ui.plotly(pie).classes("w-full")

                years: list[float] = []
                balances: list[float] = []
                for row in result.schedule:
                    if int(row["month"]) % 12 == 0 or int(row["month"]) == 1:
                        years.append(int(row["month"]) / 12)
                        balances.append(float(row["balance"]))

                cum_i = 0.0
                cum_p = 0.0
                year_labels: list[int] = []
                cum_i_vals: list[float] = []
                cum_p_vals: list[float] = []
                for row in result.schedule:
                    cum_i += float(row["interest"])
                    cum_p += float(row["principal"])
                    if int(row["month"]) % 12 == 0:
                        year_labels.append(int(row["month"]) // 12)
                        cum_i_vals.append(cum_i)
                        cum_p_vals.append(cum_p)

                if years:
                    balance_fig = go.Figure()
                    balance_fig.add_trace(
                        go.Scatter(
                            x=years,
                            y=balances,
                            mode="lines",
                            name="Remaining balance",
                            line=dict(color=_CHART["balance"], width=2.5),
                            fill="tozeroy",
                            fillcolor="rgba(0, 229, 255, 0.18)",
                            hovertemplate="Year %{x:.0f}<br>$%{y:,.0f}<extra></extra>",
                        )
                    )
                    balance_fig.update_layout(
                        **_chart_layout(
                            title=dict(
                                text="Loan balance over time",
                                x=0,
                                xanchor="left",
                                font=dict(color=_CHART["text"]),
                            ),
                            showlegend=False,
                            height=320,
                            xaxis=_axis_style(title="Year", showgrid=False),
                            yaxis=_axis_style(title="", tickformat="$,.0s"),
                        )
                    )
                    ui.plotly(balance_fig).classes("w-full")

                if year_labels:
                    stack = go.Figure()
                    stack.add_trace(
                        go.Scatter(
                            x=year_labels,
                            y=cum_p_vals,
                            name="Principal",
                            stackgroup="one",
                            line=dict(width=0.5, color=_CHART["principal"]),
                            fillcolor="rgba(0, 229, 255, 0.55)",
                            hovertemplate="Year %{x}<br>Principal $%{y:,.0f}<extra></extra>",
                        )
                    )
                    stack.add_trace(
                        go.Scatter(
                            x=year_labels,
                            y=cum_i_vals,
                            name="Interest",
                            stackgroup="one",
                            line=dict(width=0.5, color=_CHART["interest"]),
                            fillcolor="rgba(255, 43, 214, 0.55)",
                            hovertemplate="Year %{x}<br>Interest $%{y:,.0f}<extra></extra>",
                        )
                    )
                    stack.update_layout(
                        **_chart_layout(
                            title=dict(
                                text="Cumulative principal vs interest",
                                x=0,
                                xanchor="left",
                                font=dict(color=_CHART["text"]),
                            ),
                            height=320,
                            xaxis=_axis_style(title="Year", showgrid=False),
                            yaxis=_axis_style(title="", tickformat="$,.0s"),
                        )
                    )
                    ui.plotly(stack).classes("w-full")

                if result.total_interest > 0:
                    ui.label(
                        f"Total interest over the loan: {_money(result.total_interest)}"
                    ).classes("text-caption text-grey-7")

        def save() -> None:
            data = collect()
            with get_session() as session:
                PropertyService(session).update_financial(prop.id, **data)
            ui.notify("Assumptions saved", type="positive")
            redraw()

        with ui.row().classes("q-mt-md gap-2"):
            ui.button("Recalculate", on_click=redraw).props("outline dense")
            ui.button("Save assumptions", on_click=save).props("color=primary dense")

        redraw()


MODULE = ModuleSpec(id="financial", title="Financials", order=40, render=render)
