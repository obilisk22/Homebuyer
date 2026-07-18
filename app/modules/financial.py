from __future__ import annotations

from nicegui import ui

from app.core.db import get_session
from app.core.finance import (
    buy_vs_rent_projection,
    down_payment_dollars,
    down_payment_pct_from_dollars,
    effective_price,
    summarize,
)
from app.core.gemini_financial import build_financial_fingerprint
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.mortgage_rates import resolve_interest_rate, should_autofill_interest_rate
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
        ui.label(label).classes("hb-page-meta")
        ui.label(value).classes(
            "text-h5 text-weight-medium" if accent else "text-h6"
        )


def _section(title: str, *, quiet: bool = False):
    """Section column; quiet=True uses muted meta title (Loan / Ownership / Buy vs rent)."""
    col = ui.column().classes("gap-2 w-full")
    with col:
        # Deal stays hb-section-title; quiet sections use hb-page-meta (no Quasar typography).
        title_cls = "hb-page-meta" if quiet else "hb-section-title"
        ui.label(title).classes(title_cls)
    return col


def render(prop: Property, container: ui.element) -> None:
    property_id = prop.id
    live = prop
    if live.financial is None:
        # Creating a missing financial record mutates storage, so do it in a
        # fresh session; normal first paint uses the detached page property.
        with get_session() as session:
            fresh = PropertyService(session).get_property(property_id)
            assert fresh is not None
            PropertyService(session).ensure_financial(fresh)
            live = fresh

    fin = live.financial
    assert fin is not None
    list_price = float(getattr(fin, "list_price", None) or fin.purchase_price or 0)
    offer_price = float(getattr(fin, "offer_price", None) or 0)
    price0 = effective_price(list_price, offer_price)
    down_dollars0 = down_payment_dollars(price0, float(fin.down_payment_pct or 0))
    values = {
        "list_price": list_price,
        "offer_price": offer_price,
        "down_payment_dollars": down_dollars0,
        "interest_rate_pct": fin.interest_rate_pct,
        "loan_term_years": fin.loan_term_years,
        "annual_property_tax": fin.annual_property_tax,
        "annual_insurance": fin.annual_insurance,
        "monthly_hoa": fin.monthly_hoa,
        "closing_cost_pct": fin.closing_cost_pct,
        "monthly_rent": fin.monthly_rent,
        "appreciation_pct": fin.appreciation_pct,
    }
    cached_gemini = (live.financial_gemini or "").strip()
    cached_for = (live.financial_gemini_for or "").strip()
    subject_zillow_url = (live.zillow_url or "").strip()
    with get_session() as session:
        peer_refs = PropertyService(session)._library_zillow_refs(property_id)
    gemini_fp = build_financial_fingerprint(
        subject_zillow_url=subject_zillow_url,
        peer_refs=peer_refs,
    )

    with container:
        ui.label("Financials").classes("hb-page-title")
        ui.label("Offer vs list, financing, and monthly housing cost.").classes(
            "hb-page-hint"
        )

        hero = ui.row().classes("w-full gap-3 q-mt-md flex-wrap items-stretch")
        breakdown = ui.row().classes("w-full gap-3 q-mt-sm flex-wrap")

        with ui.element("div").classes("hb-financial-form w-full q-mt-lg"):
            # Four equal grid children (deal + three quiet); deal tagged for optional CSS.
            with _section("Your deal").classes("hb-financial-form__deal"):
                offer_in = ui.number(
                    "Offer price", value=values["offer_price"], format="%.0f"
                ).props("prefix=$ dense outlined stack-label").classes("w-full")
                ui.label("Leave blank to use list price for the mortgage.").classes(
                    "hb-page-meta"
                )
                with ui.row().classes("w-full items-end gap-2 no-wrap"):
                    down = ui.number(
                        "Down payment",
                        value=values["down_payment_dollars"],
                        format="%.0f",
                    ).props("prefix=$ dense outlined stack-label").classes("col")
                    down_warn = (
                        ui.icon("warning", color="amber")
                        .props("size=sm")
                        .tooltip("Under 20% — PMI may apply")
                        .classes("q-mb-sm")
                    )
                    down_warn.set_visibility(False)
                down_pct_label = ui.label("").classes("hb-page-meta")

            with _section("Loan", quiet=True):
                ui.label("Defaults — edit if needed.").classes("hb-page-meta")
                list_in = ui.number(
                    "List price", value=values["list_price"], format="%.0f"
                ).props("prefix=$ dense outlined stack-label").classes("w-full")
                rate = ui.number(
                    "Interest rate", value=values["interest_rate_pct"], format="%.3f"
                ).props("suffix=% dense outlined stack-label").classes("w-full")
                rate_src_label = ui.label(
                    (fin.interest_rate_source or "").strip()
                ).classes("hb-page-meta")
                if not (fin.interest_rate_source or "").strip():
                    rate_src_label.set_visibility(False)
                term = ui.number(
                    "Term", value=values["loan_term_years"], format="%.0f"
                ).props("suffix=years dense outlined stack-label").classes("w-full")
                closing = ui.number(
                    "Closing costs", value=values["closing_cost_pct"], format="%.1f"
                ).props("suffix=% dense outlined stack-label").classes("w-full")

            rate_source_state = {"value": (fin.interest_rate_source or "").strip()}
            suppress_rate_manual = {"on": False}

            def _show_rate_source(text: str) -> None:
                rate_source_state["value"] = text
                rate_src_label.set_text(text)
                rate_src_label.set_visibility(bool(text))

            def _apply_pmms_rate_for_term() -> None:
                if not should_autofill_interest_rate(rate_source_state["value"]):
                    return
                new_rate, src = resolve_interest_rate(int(term.value or 30))
                if new_rate is None:
                    return
                suppress_rate_manual["on"] = True
                try:
                    rate.value = new_rate
                finally:
                    suppress_rate_manual["on"] = False
                _show_rate_source(src)

            def _mark_rate_manual(_: object = None) -> None:
                if suppress_rate_manual["on"]:
                    return
                _show_rate_source("Manual")

            term.on_value_change(lambda _: _apply_pmms_rate_for_term())
            rate.on_value_change(_mark_rate_manual)

            with _section("Ownership costs", quiet=True):
                ui.label("Usually filled from the listing.").classes("hb-page-meta")
                tax = ui.number(
                    "Property tax / year",
                    value=values["annual_property_tax"],
                    format="%.0f",
                ).props("prefix=$ dense outlined stack-label").classes("w-full")
                if (fin.property_tax_source or "").strip():
                    ui.label(fin.property_tax_source).classes("hb-page-meta")
                insurance = ui.number(
                    "Insurance / year",
                    value=values["annual_insurance"],
                    format="%.0f",
                ).props("prefix=$ dense outlined stack-label").classes("w-full")
                if (fin.insurance_source or "").strip():
                    ui.label(fin.insurance_source).classes("hb-page-meta")
                hoa = ui.number(
                    "HOA / month", value=values["monthly_hoa"], format="%.0f"
                ).props("prefix=$ dense outlined stack-label").classes("w-full")

            with _section("Buy vs rent", quiet=True):
                ui.label(
                    "Compare selling equity with investing the monthly difference."
                ).classes("hb-page-meta")
                rent_in = ui.number(
                    "Comparable rent / month",
                    value=values["monthly_rent"],
                    format="%.0f",
                ).props("prefix=$ dense outlined stack-label").classes("w-full")
                if (fin.rent_source or "").strip():
                    ui.label(fin.rent_source).classes("hb-page-meta")
                appr_in = ui.number(
                    "Appreciation",
                    value=values["appreciation_pct"],
                    format="%.2f",
                ).props("suffix=%/yr dense outlined stack-label").classes("w-full")
                appreciation_bits = [(fin.appreciation_source or "").strip()]
                if fin.appreciation_fhfa_pct is not None:
                    appreciation_bits.append(f"FHFA {fin.appreciation_fhfa_pct:.2f}%")
                if fin.appreciation_zillow_pct is not None:
                    appreciation_bits.append(
                        f"Zillow {fin.appreciation_zillow_pct:.2f}%"
                    )
                if any(appreciation_bits):
                    ui.label(" · ".join(bit for bit in appreciation_bits if bit)).classes(
                        "hb-page-meta"
                    )

        charts = ui.column().classes("w-full q-mt-lg gap-2")

        def _basis_word(offer_val: float) -> str:
            return "offer" if offer_val > 0 else "list"

        def refresh_down_meta() -> None:
            offer_val = float(offer_in.value or 0)
            list_val = float(list_in.value or 0)
            price = effective_price(list_val, offer_val)
            dollars = float(down.value or 0)
            pct = down_payment_pct_from_dollars(price, dollars)
            if price > 0:
                down_pct_label.set_text(f"≈ {pct:.1f}% of {_basis_word(offer_val)}")
            else:
                down_pct_label.set_text(
                    "Set a list or offer price to size the down payment."
                )
            down_warn.set_visibility(price > 0 and pct < 20.0)

        def collect() -> dict:
            offer_val = float(offer_in.value or 0)
            list_val = float(list_in.value or 0)
            price = effective_price(list_val, offer_val)
            dollars = float(down.value or 0)
            return {
                "list_price": list_val,
                "offer_price": offer_val,
                "down_payment_pct": down_payment_pct_from_dollars(price, dollars),
                "interest_rate_pct": float(rate.value or 0),
                "loan_term_years": int(term.value or 30),
                "annual_property_tax": float(tax.value or 0),
                "annual_insurance": float(insurance.value or 0),
                "monthly_hoa": float(hoa.value or 0),
                "closing_cost_pct": float(closing.value or 0),
                "monthly_rent": float(rent_in.value or 0),
                "appreciation_pct": float(appr_in.value or 0),
            }

        def mortgage_data(data: dict) -> dict:
            return {
                key: value
                for key, value in data.items()
                if key not in {"monthly_rent", "appreciation_pct"}
            }

        offer_in.on_value_change(lambda _: refresh_down_meta())
        list_in.on_value_change(lambda _: refresh_down_meta())
        down.on_value_change(lambda _: refresh_down_meta())

        gemini_state = {"text": cached_gemini, "for": cached_for}

        def redraw() -> None:
            import plotly.graph_objects as go

            refresh_down_meta()
            data = collect()
            result = summarize(**mortgage_data(data))

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
                        ui.label(label).classes("hb-page-meta")
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

                if result.effective_price > 0:
                    projection = buy_vs_rent_projection(
                        summary=result,
                        appreciation_pct=float(appr_in.value or 0),
                        monthly_rent=float(rent_in.value or 0),
                    )
                    buy_vs_rent = go.Figure()
                    buy_vs_rent.add_trace(
                        go.Scatter(
                            x=[row.year for row in projection],
                            y=[row.buy_net_worth for row in projection],
                            name="Buy (sell net)",
                            line=dict(color=_CHART["pi"], width=2.5),
                            hovertemplate=(
                                "Year %{x}<br>Buy $%{y:,.0f}<extra></extra>"
                            ),
                        )
                    )
                    buy_vs_rent.add_trace(
                        go.Scatter(
                            x=[row.year for row in projection],
                            y=[row.rent_invest_net_worth for row in projection],
                            name="Rent + invest 10%",
                            line=dict(color=_CHART["interest"], width=2.5),
                            hovertemplate=(
                                "Year %{x}<br>Rent+invest $%{y:,.0f}<extra></extra>"
                            ),
                        )
                    )
                    buy_vs_rent.update_layout(
                        **_chart_layout(
                            title=dict(
                                text="Buy vs rent + invest (net worth)",
                                x=0,
                                xanchor="left",
                                font=dict(color=_CHART["text"]),
                            ),
                            height=360,
                            xaxis=_axis_style(title="Year", showgrid=False),
                            yaxis=_axis_style(title="", tickformat="$,.0s"),
                        )
                    )
                    ui.plotly(buy_vs_rent).classes("w-full")

                    projection_bits = [
                        f"Appreciation {float(appr_in.value or 0):.2f}%/yr",
                        f"source {fin.appreciation_source or '—'}",
                    ]
                    if fin.appreciation_fhfa_pct is not None:
                        projection_bits.append(
                            f"FHFA {fin.appreciation_fhfa_pct:.2f}%"
                        )
                    if fin.appreciation_zillow_pct is not None:
                        projection_bits.append(
                            f"Zillow {fin.appreciation_zillow_pct:.2f}%"
                        )
                    projection_bits.extend(["sell cost 6%", "invest return 10%"])
                    if float(rent_in.value or 0) <= 0:
                        projection_bits.append("set rent for a fair compare")
                    ui.label(" · ".join(projection_bits)).classes("hb-page-meta")
                else:
                    ui.label(
                        "Set a list or offer price to compare buying and renting."
                    ).classes("hb-page-meta")

                if result.total_interest > 0:
                    ui.label(
                        f"Total interest over the loan: {_money(result.total_interest)}"
                    ).classes("hb-page-meta")

            refresh_gemini_panel()

        def save() -> None:
            data = collect()
            with get_session() as session:
                PropertyService(session).update_financial(property_id, **data)
            ui.notify("Assumptions saved", type="positive")
            redraw()

        for field in (
            offer_in,
            down,
            list_in,
            rate,
            term,
            closing,
            tax,
            insurance,
            hoa,
            rent_in,
            appr_in,
        ):
            field.on("keydown.enter", lambda: redraw())

        with ui.row().classes("q-mt-md gap-2"):
            ui.button("Recalculate", on_click=redraw).props("outline dense")
            ui.button("Save assumptions", on_click=save).props(
                "unelevated color=primary dense"
            )

        ui.separator().classes("q-mt-lg").style("border-color: var(--hb-border);")
        ui.label("Gemini financial take").classes("hb-section-title q-mt-md")
        ui.label(
            "Gemini reads the Zillow listing URLs for this home and your other library "
            "homes (URL context) — opinion on market, location, and buy vs rent. "
            "Ask or Regenerate below."
        ).classes("hb-page-hint")
        gemini_controls = ui.row().classes("w-full gap-2 q-mt-sm flex-wrap items-center")
        gemini_box = ui.column().classes("w-full gap-2 q-mt-sm")

        def run_gemini(*, force: bool) -> None:
            """ensure_gemini_financial → refresh panel in place (no remount)."""
            try:
                ui.notify(
                    "Generating financial take from Zillow…",
                    type="ongoing",
                    timeout=0,
                )
                with get_session() as session:
                    svc = PropertyService(session)
                    # Persist current form so buy/rent UI stays in sync; Gemini
                    # itself reads Zillow URLs, not these calculator fields.
                    svc.update_financial(property_id, **collect())
                    prop = svc.ensure_gemini_financial(property_id, force=force)
                    gemini_state["text"] = (prop.financial_gemini or "").strip()
                    gemini_state["for"] = (prop.financial_gemini_for or "").strip()
                    nonlocal gemini_fp, subject_zillow_url, peer_refs
                    subject_zillow_url = (prop.zillow_url or "").strip()
                    peer_refs = svc._library_zillow_refs(property_id)
                    gemini_fp = build_financial_fingerprint(
                        subject_zillow_url=subject_zillow_url,
                        peer_refs=peer_refs,
                    )
                refresh_gemini_panel()
                ui.notify("Financial take ready", type="positive")
            except Exception as exc:  # noqa: BLE001
                ui.notify(f"Gemini failed: {exc}", type="negative")

        def refresh_gemini_panel() -> None:
            fp = gemini_fp
            text = gemini_state["text"]
            stale = bool(text) and gemini_state["for"] and gemini_state["for"] != fp

            gemini_controls.clear()
            with gemini_controls:
                if text and not stale:
                    ui.button(
                        "Regenerate",
                        on_click=lambda: run_gemini(force=True),
                        icon="auto_awesome",
                    ).props("outline color=primary dense")
                else:
                    label = "Regenerate" if text else "Ask Gemini"
                    ui.button(
                        label,
                        on_click=lambda: run_gemini(force=True),
                        icon="auto_awesome",
                    ).props("unelevated color=primary dense")

            gemini_box.clear()
            with gemini_box:
                if text and not stale:
                    ui.markdown(text).classes("hb-gemini-prose")
                elif text and stale:
                    ui.label(
                        "Zillow links in your library changed since this AI take — "
                        "Regenerate so Gemini re-reads the current listing URLs."
                    ).classes("hb-page-meta")
                    with ui.expansion(
                        "Previous AI take (outdated)", icon="history"
                    ).classes("w-full"):
                        ui.markdown(text).classes(
                            "hb-gemini-prose hb-gemini-prose--stale"
                        )
                else:
                    ui.label(
                        "Ask Gemini to open this home’s Zillow page (and your other "
                        "saved Zillow links) for a market / buy-vs-rent opinion."
                    ).classes("hb-empty-state w-full")

        redraw()


MODULE = ModuleSpec(id="financial", title="Financials", order=40, render=render)
