from __future__ import annotations

from nicegui import run, ui

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
from app.core.ui_jobs import ensure_gemini_financial_job

# Neon cyberpunk chart palette (cyan / magenta / lime / amber)
_CHART = {
    "pi": "#00E5FF",
    "tax": "#FF2BD6",
    "ins": "#B8FF3C",
    "hoa": "#FFC107",
    "pmi": "#FF6B9D",
    "maint": "#7CFFB2",
    "utils": "#5B8CFF",
    "interest": "#FF2BD6",
    "paper": "#12151A",
    "plot": "#0B0D10",
    "grid": "rgba(0, 229, 255, 0.12)",
    "text": "#E8EDF4",
    "muted": "#8B96A8",
}

# How defaults / autofills are calculated (TODO-033).
_FIELD_HELP: dict[str, str] = {
    "offer_price": (
        "Optional. When set, mortgage math uses offer instead of list. "
        "Revert clears offer so list price drives the loan."
    ),
    "down_payment_dollars": (
        "Stored as a percent of effective price (offer if set, else list). "
        "Product default is 20%. Under 20% may trigger PMI."
    ),
    "list_price": (
        "Filled from the Zillow listing on add/refresh. "
        "Revert restores the listing price stored on the property."
    ),
    "interest_rate_pct": (
        "Autofilled from Freddie Mac PMMS weekly averages — the closer of "
        "15-yr vs 30-yr FRM for your loan term. Edit → Manual; revert reloads PMMS."
    ),
    "loan_term_years": "Product default 30 years. Changing term refreshes PMMS when not Manual.",
    "closing_cost_pct": "Product default 3% of effective price (cash to close).",
    "annual_property_tax": (
        "Chain: Zillow annual tax → assessed × rate → ACS county effective rate "
        "× assessed-or-list basis (needs CENSUS_API_KEY). Revert re-resolves from location."
    ),
    "annual_insurance": (
        "Prefers Zillow modeled homeowners insurance; else state average premium "
        "scaled to list price. Revert re-resolves from state table when listing is absent."
    ),
    "monthly_hoa": "From the Zillow listing HOA fee when present. Revert uses listing HOA.",
    "monthly_maintenance": (
        "Age-blend reserve (% of price + $/sqft × state index) averaged with Angi "
        "national maint+emergency, then ÷12. Edit → Manual; revert recomputes."
    ),
    "monthly_utilities": (
        "Provider from city/ZIP (LADWP vs SCE + SoCalGas in LA-area; else Default) "
        "× sqft × age efficiency factor + water/trash. Edit → Manual; revert recomputes."
    ),
    "monthly_rent": (
        "Prefers Zillow rentZestimate; else $5,300 / Default. "
        "Revert restores the $5,300 Default baseline."
    ),
    "rent_control": (
        "When checked, rent growth is fixed at 2%/yr. Unchecked → ACS county "
        "median-rent ~5y CAGR (or 3% Default)."
    ),
    "appreciation_pct": (
        "Blend of FHFA ZIP5 ~10y CAGR and Zillow decade %, or 3% Default when both missing. "
        "Revert re-blends stored FHFA/Zillow components."
    ),
    "invest_return_pct": "Assumed return on surplus / rent+invest portfolio. Product default 10%/yr.",
    "selling_cost_pct": "Assumed closing/selling costs when comparing buy equity. Product default 6%.",
    "monthly_budget": (
        "Shared housing budget: both buy and rent paths invest max(0, budget − housing cost). "
        "Default $13,000/mo."
    ),
    "marginal_tax_pct": (
        "CA MFJ-style combined rate for the interest + SALT-capped property-tax shield. "
        "Default 41%."
    ),
    "cg_tax_pct": "~15% federal LTCG + ~9% CA (editable). Default 24%.",
    "cg_exclusion": "Primary-residence capital-gains exclusion. MFJ default $500,000.",
    "salt_cap": "Federal SALT cap on the property-tax deduction in the tax shield. Default $10,000.",
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


def _field_chrome(help_key: str, on_revert) -> None:
    """Low-opacity ? help + restart revert control beside a field."""
    with ui.row().classes("items-center gap-1 no-wrap hb-field-chrome"):
        tip = _FIELD_HELP.get(help_key, "")
        if tip:
            (
                ui.icon("help_outline")
                .props("size=xs")
                .classes("hb-field-help")
                .tooltip(tip)
            )
        (
            ui.button(icon="restart_alt", on_click=on_revert)
            .props("flat dense round size=sm")
            .classes("hb-field-revert")
            .tooltip("Revert to default")
        )


def _source_caption(text: str):
    """Short live source line (optional; quiet)."""
    label = ui.label((text or "").strip()).classes("hb-page-meta hb-field-source")
    if not (text or "").strip():
        label.set_visibility(False)
    return label


def render(prop: Property, container: ui.element) -> None:
    property_id = prop.id
    # Always ensure_financial so maintenance/utilities/PMMS backfill on tab open.
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
        "invest_return_pct": float(getattr(fin, "invest_return_pct", None) or 10.0),
        "selling_cost_pct": float(getattr(fin, "selling_cost_pct", None) or 6.0),
        "monthly_maintenance": float(getattr(fin, "monthly_maintenance", None) or 0.0),
        "monthly_utilities": float(getattr(fin, "monthly_utilities", None) or 0.0),
        "monthly_budget": float(getattr(fin, "monthly_budget", None) or 13_000.0),
        "marginal_tax_pct": float(getattr(fin, "marginal_tax_pct", None) or 41.0),
        "cg_tax_pct": float(getattr(fin, "cg_tax_pct", None) or 24.0),
        "cg_exclusion": float(getattr(fin, "cg_exclusion", None) or 500_000.0),
        "salt_cap": float(getattr(fin, "salt_cap", None) or 10_000.0),
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
    growth_state = {
        "pct": float(fin.rent_growth_pct or 0),
        "source": (fin.rent_growth_source or "").strip() or "Default",
        "control": bool(fin.rent_control),
    }
    appr_source_state = {
        "source": (fin.appreciation_source or "").strip(),
        "fhfa": fin.appreciation_fhfa_pct,
        "zillow": fin.appreciation_zillow_pct,
    }

    with container:
        ui.label("Financials").classes("hb-page-title")
        ui.label("Offer vs list, financing, and monthly housing cost.").classes(
            "hb-page-hint"
        )

        hero = ui.row().classes("w-full gap-3 q-mt-md flex-wrap items-stretch")
        breakdown = ui.row().classes("w-full gap-3 q-mt-sm flex-wrap")

        with ui.element("div").classes("hb-financial-form w-full q-mt-lg"):
            # —— Primary: Your deal ——
            with ui.column().classes("gap-2 w-full hb-financial-form__deal"):
                ui.label("Your deal").classes("hb-section-title")
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    ui.label("Offer price").classes("hb-field-label")
                    _field_chrome("offer_price", lambda: _revert("offer_price"))
                offer_in = ui.number(
                    label=None, value=values["offer_price"], format="%.0f"
                ).props("prefix=$ dense outlined").classes("w-full")
                with ui.row().classes("w-full items-end gap-2 no-wrap"):
                    with ui.column().classes("col gap-1"):
                        with ui.row().classes(
                            "w-full items-center justify-between no-wrap"
                        ):
                            ui.label("Down payment").classes("hb-field-label")
                            _field_chrome(
                                "down_payment_dollars",
                                lambda: _revert("down_payment_pct"),
                            )
                        down = ui.number(
                            label=None,
                            value=values["down_payment_dollars"],
                            format="%.0f",
                        ).props("prefix=$ dense outlined").classes("w-full")
                    down_warn = (
                        ui.icon("warning", color="amber")
                        .props("size=sm")
                        .tooltip("Under 20% — PMI may apply")
                        .classes("q-mb-sm")
                    )
                    down_warn.set_visibility(False)
                down_pct_label = ui.label("").classes("hb-page-meta")

            # —— Primary: Rent compare ——
            with ui.column().classes("gap-2 w-full hb-financial-form__rent"):
                ui.label("Buy vs rent").classes("hb-section-title")
                with ui.row().classes("w-full items-end gap-2 no-wrap"):
                    with ui.column().classes("col gap-1"):
                        with ui.row().classes(
                            "w-full items-center justify-between no-wrap"
                        ):
                            ui.label("Comparable rent / month").classes("hb-field-label")
                            _field_chrome("monthly_rent", lambda: _revert("monthly_rent"))
                        rent_in = ui.number(
                            label=None,
                            value=values["monthly_rent"],
                            format="%.0f",
                        ).props("prefix=$ dense outlined").classes("w-full")
                    with ui.row().classes("items-center gap-1 no-wrap q-mb-xs"):
                        rent_control = ui.checkbox(
                            "Rent control", value=growth_state["control"]
                        ).props("dense")
                        _field_chrome("rent_control", lambda: _revert("rent_control"))
                rent_src_label = _source_caption(fin.rent_source or "")
                growth_caption = ui.label("").classes("hb-page-meta")

        # —— Collapsed: Loan / Ownership / Advanced ——
        with ui.column().classes("w-full gap-2 q-mt-md"):
            with ui.expansion("Loan", icon="account_balance").classes(
                "w-full hb-financial-expansion"
            ):
                with ui.column().classes("gap-2 w-full q-pt-sm"):
                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("List price").classes("hb-field-label")
                        _field_chrome("list_price", lambda: _revert("list_price"))
                    list_in = ui.number(
                        label=None, value=values["list_price"], format="%.0f"
                    ).props("prefix=$ dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Interest rate").classes("hb-field-label")
                        _field_chrome(
                            "interest_rate_pct", lambda: _revert("interest_rate_pct")
                        )
                    rate = ui.number(
                        label=None, value=values["interest_rate_pct"], format="%.3f"
                    ).props("suffix=% dense outlined").classes("w-full")
                    rate_src_label = _source_caption(fin.interest_rate_source or "")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Term").classes("hb-field-label")
                        _field_chrome(
                            "loan_term_years", lambda: _revert("loan_term_years")
                        )
                    term = ui.number(
                        label=None, value=values["loan_term_years"], format="%.0f"
                    ).props("suffix=years dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Closing costs").classes("hb-field-label")
                        _field_chrome(
                            "closing_cost_pct", lambda: _revert("closing_cost_pct")
                        )
                    closing = ui.number(
                        label=None, value=values["closing_cost_pct"], format="%.1f"
                    ).props("suffix=% dense outlined").classes("w-full")

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

            with ui.expansion("Ownership costs", icon="home").classes(
                "w-full hb-financial-expansion"
            ):
                with ui.column().classes("gap-2 w-full q-pt-sm"):
                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Property tax / year").classes("hb-field-label")
                        _field_chrome(
                            "annual_property_tax",
                            lambda: _revert("annual_property_tax"),
                        )
                    tax = ui.number(
                        label=None,
                        value=values["annual_property_tax"],
                        format="%.0f",
                    ).props("prefix=$ dense outlined").classes("w-full")
                    tax_src_label = _source_caption(fin.property_tax_source or "")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Insurance / year").classes("hb-field-label")
                        _field_chrome(
                            "annual_insurance", lambda: _revert("annual_insurance")
                        )
                    insurance = ui.number(
                        label=None,
                        value=values["annual_insurance"],
                        format="%.0f",
                    ).props("prefix=$ dense outlined").classes("w-full")
                    ins_src_label = _source_caption(fin.insurance_source or "")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("HOA / month").classes("hb-field-label")
                        _field_chrome("monthly_hoa", lambda: _revert("monthly_hoa"))
                    hoa = ui.number(
                        label=None, value=values["monthly_hoa"], format="%.0f"
                    ).props("prefix=$ dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Maintenance / month").classes("hb-field-label")
                        _field_chrome(
                            "monthly_maintenance",
                            lambda: _revert("monthly_maintenance"),
                        )
                    maint_in = ui.number(
                        label=None,
                        value=values["monthly_maintenance"],
                        format="%.0f",
                    ).props("prefix=$ dense outlined").classes("w-full")
                    maint_src_label = _source_caption(fin.maintenance_source or "")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Utilities / month").classes("hb-field-label")
                        _field_chrome(
                            "monthly_utilities",
                            lambda: _revert("monthly_utilities"),
                        )
                    utils_in = ui.number(
                        label=None,
                        value=values["monthly_utilities"],
                        format="%.0f",
                    ).props("prefix=$ dense outlined").classes("w-full")
                    utils_src_label = _source_caption(fin.utilities_source or "")

            with ui.expansion("Advanced buy vs rent", icon="tune").classes(
                "w-full hb-financial-expansion"
            ):
                with ui.column().classes("gap-2 w-full q-pt-sm"):
                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Appreciation").classes("hb-field-label")
                        _field_chrome(
                            "appreciation_pct", lambda: _revert("appreciation_pct")
                        )
                    appr_in = ui.number(
                        label=None,
                        value=values["appreciation_pct"],
                        format="%.2f",
                    ).props("suffix=%/yr dense outlined").classes("w-full")
                    appr_bits = [appr_source_state["source"]]
                    if appr_source_state["fhfa"] is not None:
                        appr_bits.append(f"FHFA {appr_source_state['fhfa']:.2f}%")
                    if appr_source_state["zillow"] is not None:
                        appr_bits.append(
                            f"Zillow {appr_source_state['zillow']:.2f}%"
                        )
                    appr_src_label = _source_caption(
                        " · ".join(bit for bit in appr_bits if bit)
                    )

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Invest return").classes("hb-field-label")
                        _field_chrome(
                            "invest_return_pct", lambda: _revert("invest_return_pct")
                        )
                    invest_in = ui.number(
                        label=None,
                        value=values["invest_return_pct"],
                        format="%.2f",
                    ).props("suffix=%/yr dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Sell cost").classes("hb-field-label")
                        _field_chrome(
                            "selling_cost_pct", lambda: _revert("selling_cost_pct")
                        )
                    sell_in = ui.number(
                        label=None,
                        value=values["selling_cost_pct"],
                        format="%.2f",
                    ).props("suffix=% dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Housing budget / month").classes("hb-field-label")
                        _field_chrome(
                            "monthly_budget", lambda: _revert("monthly_budget")
                        )
                    budget_in = ui.number(
                        label=None,
                        value=values["monthly_budget"],
                        format="%.0f",
                    ).props("prefix=$ dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Marginal tax rate").classes("hb-field-label")
                        _field_chrome(
                            "marginal_tax_pct", lambda: _revert("marginal_tax_pct")
                        )
                    tax_rate_in = ui.number(
                        label=None,
                        value=values["marginal_tax_pct"],
                        format="%.1f",
                    ).props("suffix=% dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("Capital gains rate").classes("hb-field-label")
                        _field_chrome("cg_tax_pct", lambda: _revert("cg_tax_pct"))
                    cg_rate_in = ui.number(
                        label=None, value=values["cg_tax_pct"], format="%.1f"
                    ).props("suffix=% dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("CG exclusion").classes("hb-field-label")
                        _field_chrome("cg_exclusion", lambda: _revert("cg_exclusion"))
                    cg_excl_in = ui.number(
                        label=None, value=values["cg_exclusion"], format="%.0f"
                    ).props("prefix=$ dense outlined").classes("w-full")

                    with ui.row().classes(
                        "w-full items-center justify-between no-wrap"
                    ):
                        ui.label("SALT cap").classes("hb-field-label")
                        _field_chrome("salt_cap", lambda: _revert("salt_cap"))
                    salt_in = ui.number(
                        label=None, value=values["salt_cap"], format="%.0f"
                    ).props("prefix=$ dense outlined").classes("w-full")

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
                "rent_control": bool(growth_state["control"]),
                "rent_growth_pct": float(growth_state["pct"] or 0),
                "appreciation_pct": float(appr_in.value or 0),
                "invest_return_pct": float(invest_in.value or 0),
                "selling_cost_pct": float(sell_in.value or 0),
                "monthly_maintenance": float(maint_in.value or 0),
                "monthly_utilities": float(utils_in.value or 0),
                "monthly_budget": float(budget_in.value or 0),
                "marginal_tax_pct": float(tax_rate_in.value or 0),
                "cg_tax_pct": float(cg_rate_in.value or 0),
                "cg_exclusion": float(cg_excl_in.value or 0),
                "salt_cap": float(salt_in.value or 0),
            }

        def mortgage_data(data: dict) -> dict:
            return {
                key: value
                for key, value in data.items()
                if key
                not in {
                    "monthly_rent",
                    "rent_control",
                    "rent_growth_pct",
                    "appreciation_pct",
                    "invest_return_pct",
                    "selling_cost_pct",
                    "monthly_budget",
                    "marginal_tax_pct",
                    "cg_tax_pct",
                    "cg_exclusion",
                    "salt_cap",
                }
            }

        def _apply_reverted(saved) -> None:
            """Push reverted DB values into live inputs + captions."""
            nonlocal price0
            list_val = float(getattr(saved, "list_price", None) or 0)
            offer_val = float(getattr(saved, "offer_price", None) or 0)
            price0 = effective_price(list_val, offer_val)
            list_in.value = list_val
            offer_in.value = offer_val
            down.value = down_payment_dollars(
                price0, float(saved.down_payment_pct or 0)
            )
            rate.value = float(saved.interest_rate_pct or 0)
            _show_rate_source((saved.interest_rate_source or "").strip())
            term.value = int(saved.loan_term_years or 30)
            closing.value = float(saved.closing_cost_pct or 0)
            tax.value = float(saved.annual_property_tax or 0)
            tax_src = (saved.property_tax_source or "").strip()
            tax_src_label.set_text(tax_src)
            tax_src_label.set_visibility(bool(tax_src))
            insurance.value = float(saved.annual_insurance or 0)
            ins_src = (saved.insurance_source or "").strip()
            ins_src_label.set_text(ins_src)
            ins_src_label.set_visibility(bool(ins_src))
            hoa.value = float(saved.monthly_hoa or 0)
            maint_in.value = float(saved.monthly_maintenance or 0)
            ms = (saved.maintenance_source or "").strip()
            maint_src_label.set_text(ms)
            maint_src_label.set_visibility(bool(ms))
            utils_in.value = float(getattr(saved, "monthly_utilities", None) or 0)
            us = (getattr(saved, "utilities_source", None) or "").strip()
            utils_src_label.set_text(us)
            utils_src_label.set_visibility(bool(us))
            rent_in.value = float(saved.monthly_rent or 0)
            rs = (saved.rent_source or "").strip()
            rent_src_label.set_text(rs)
            rent_src_label.set_visibility(bool(rs))
            growth_state["control"] = bool(saved.rent_control)
            growth_state["pct"] = float(saved.rent_growth_pct or 0)
            growth_state["source"] = (
                saved.rent_growth_source or ""
            ).strip() or "Default"
            rent_control.value = growth_state["control"]
            appr_in.value = float(saved.appreciation_pct or 0)
            appr_source_state["source"] = (saved.appreciation_source or "").strip()
            appr_source_state["fhfa"] = saved.appreciation_fhfa_pct
            appr_source_state["zillow"] = saved.appreciation_zillow_pct
            bits = [appr_source_state["source"]]
            if appr_source_state["fhfa"] is not None:
                bits.append(f"FHFA {appr_source_state['fhfa']:.2f}%")
            if appr_source_state["zillow"] is not None:
                bits.append(f"Zillow {appr_source_state['zillow']:.2f}%")
            appr_txt = " · ".join(b for b in bits if b)
            appr_src_label.set_text(appr_txt)
            appr_src_label.set_visibility(bool(appr_txt))
            invest_in.value = float(saved.invest_return_pct or 10)
            sell_in.value = float(saved.selling_cost_pct or 6)
            budget_in.value = float(saved.monthly_budget or 13_000)
            tax_rate_in.value = float(saved.marginal_tax_pct or 41)
            cg_rate_in.value = float(saved.cg_tax_pct or 24)
            cg_excl_in.value = float(saved.cg_exclusion or 500_000)
            salt_in.value = float(saved.salt_cap or 10_000)

        def _revert(field: str) -> None:
            with get_session() as session:
                saved = PropertyService(session).revert_financial_field(
                    property_id, field
                )
            _apply_reverted(saved)
            ui.notify(f"Reverted {field.replace('_', ' ')}", type="info")
            redraw()

        offer_in.on_value_change(lambda _: refresh_down_meta())
        list_in.on_value_change(lambda _: refresh_down_meta())
        down.on_value_change(lambda _: refresh_down_meta())

        gemini_state = {"text": cached_gemini, "for": cached_for}

        def refresh_growth_caption() -> None:
            growth_caption.set_text(
                f"Growth {float(growth_state['pct'] or 0):.2f}%/yr · "
                f"{growth_state['source'] or 'Default'}"
            )

        def redraw() -> None:
            import plotly.graph_objects as go

            refresh_down_meta()
            refresh_growth_caption()
            data = collect()
            result = summarize(**mortgage_data(data))

            hero.clear()
            with hero:
                _summary_card(
                    "Monthly payment",
                    _money_exact(result.monthly_owner_total),
                    accent=True,
                )
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
                if result.monthly_maintenance > 0:
                    parts.append(("Maint", result.monthly_maintenance))
                if result.monthly_utilities > 0:
                    parts.append(("Utils", result.monthly_utilities))
                for label, val in parts:
                    with ui.column().classes("hb-metric px-3 py-2").style(
                        "min-width: 6.5rem"
                    ):
                        ui.label(label).classes("hb-page-meta")
                        ui.label(_money_exact(val)).classes(
                            "text-body1 text-weight-medium"
                        )

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
                if result.monthly_maintenance > 0:
                    pie_labels.append("Maintenance")
                    pie_values.append(result.monthly_maintenance)
                    pie_colors.append(_CHART["maint"])
                if result.monthly_utilities > 0:
                    pie_labels.append("Utilities")
                    pie_values.append(result.monthly_utilities)
                    pie_colors.append(_CHART["utils"])

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
                                    text=_money(result.monthly_owner_total),
                                    x=0.5,
                                    y=0.5,
                                    font=dict(size=18, color="#00E5FF"),
                                    showarrow=False,
                                )
                            ],
                        )
                    )
                    ui.plotly(pie).classes("w-full")

                if result.effective_price > 0:
                    invest_pct = float(invest_in.value or 0)
                    sell_pct = float(sell_in.value or 0)
                    maint = float(maint_in.value or 0)
                    utils = float(utils_in.value or 0)
                    budget = float(budget_in.value or 0)
                    marg = float(tax_rate_in.value or 0)
                    cg_pct = float(cg_rate_in.value or 0)
                    cg_excl = float(cg_excl_in.value or 0)
                    salt = float(salt_in.value or 0)
                    projection = buy_vs_rent_projection(
                        summary=result,
                        appreciation_pct=float(appr_in.value or 0),
                        monthly_rent=float(rent_in.value or 0),
                        rent_growth_pct=float(growth_state["pct"] or 0),
                        invest_return_pct=invest_pct,
                        selling_cost_pct=sell_pct,
                        monthly_maintenance=maint,
                        monthly_utilities=utils,
                        monthly_budget=budget,
                        marginal_tax_pct=marg,
                        cg_tax_pct=cg_pct,
                        cg_exclusion=cg_excl,
                        salt_cap=salt,
                        annual_property_tax=float(tax.value or 0),
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
                            name=f"Rent + invest {invest_pct:.0f}%",
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
                        f"source {appr_source_state['source'] or '—'}",
                        (
                            f"Rent growth {float(growth_state['pct'] or 0):.2f}%/yr"
                            f" · {growth_state['source'] or 'Default'}"
                        ),
                    ]
                    if appr_source_state["fhfa"] is not None:
                        projection_bits.append(
                            f"FHFA {appr_source_state['fhfa']:.2f}%"
                        )
                    if appr_source_state["zillow"] is not None:
                        projection_bits.append(
                            f"Zillow {appr_source_state['zillow']:.2f}%"
                        )
                    projection_bits.extend(
                        [
                            f"sell cost {sell_pct:.1f}%",
                            f"invest return {invest_pct:.1f}%",
                            f"budget {_money(budget)}/mo",
                            f"tax shield {marg:.0f}%",
                            f"CG {cg_pct:.0f}% after {_money(cg_excl)} excl",
                        ]
                    )
                    if maint > 0:
                        projection_bits.append(f"maintenance {_money(maint)}/mo")
                    if utils > 0:
                        projection_bits.append(f"utilities {_money(utils)}/mo")
                    if float(rent_in.value or 0) <= 0:
                        projection_bits.append("set rent for a fair compare")
                    ui.label(" · ".join(projection_bits)).classes("hb-page-meta")
                    ui.label(
                        "Buy NW = sale proceeds − loan − CG tax + surplus portfolio; "
                        "both paths invest leftover budget (simplified CA MFJ taxes)."
                    ).classes("hb-page-meta")
                else:
                    ui.label(
                        "Set a list or offer price to compare buying and renting."
                    ).classes("hb-page-meta")

                if result.total_interest > 0:
                    ui.label(
                        f"Total interest over the loan: {_money(result.total_interest)}"
                    ).classes("hb-page-meta")

            refresh_gemini_panel()

        def on_rent_control(_: object = None) -> None:
            checked = bool(rent_control.value)
            with get_session() as session:
                resolved = PropertyService(session).ensure_rent_growth(
                    property_id, rent_control=checked
                )
                growth_state["control"] = bool(resolved.rent_control)
                growth_state["pct"] = float(resolved.rent_growth_pct or 0)
                growth_state["source"] = (
                    resolved.rent_growth_source or ""
                ).strip() or "Default"
            refresh_growth_caption()
            redraw()

        rent_control.on_value_change(on_rent_control)

        def save() -> None:
            data = collect()
            with get_session() as session:
                saved = PropertyService(session).update_financial(property_id, **data)
                growth_state["control"] = bool(saved.rent_control)
                growth_state["pct"] = float(saved.rent_growth_pct or 0)
                growth_state["source"] = (
                    saved.rent_growth_source or ""
                ).strip() or "Default"
                ms = (saved.maintenance_source or "").strip()
                maint_src_label.set_text(ms)
                maint_src_label.set_visibility(bool(ms))
                us = (saved.utilities_source or "").strip()
                utils_src_label.set_text(us)
                utils_src_label.set_visibility(bool(us))
                rs = (saved.rent_source or "").strip()
                rent_src_label.set_text(rs)
                rent_src_label.set_visibility(bool(rs))
                _show_rate_source((saved.interest_rate_source or "").strip())
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
            invest_in,
            sell_in,
            maint_in,
            utils_in,
            budget_in,
            tax_rate_in,
            cg_rate_in,
            cg_excl_in,
            salt_in,
        ):
            field.on("keydown.enter", lambda: redraw())

        with ui.row().classes("q-mt-md gap-2"):
            ui.button("Recalculate", on_click=redraw).props(
                "unelevated dense color=dark"
            )
            ui.button("Save assumptions", on_click=save).props(
                "unelevated dense color=dark"
            ).classes("hb-btn-cta")

        ui.separator().classes("q-mt-lg").style("border-color: var(--hb-border);")
        ui.label("Gemini financial take").classes("hb-section-title q-mt-md")
        ui.label(
            "Gemini reads the Zillow listing URLs for this home and your other library "
            "homes (URL context) — opinion on market, location, and buy vs rent. "
            "Ask or Regenerate below."
        ).classes("hb-page-hint")
        gemini_controls = ui.row().classes("w-full gap-2 q-mt-sm flex-wrap items-center")
        gemini_box = ui.column().classes("w-full gap-2 q-mt-sm")

        async def run_gemini(*, force: bool) -> None:
            """ensure_gemini_financial → refresh panel in place (no remount)."""
            try:
                ui.notify(
                    "Generating financial take from Zillow…",
                    type="ongoing",
                    timeout=0,
                )
                fields = collect()
                result = await run.io_bound(
                    ensure_gemini_financial_job, property_id, fields, force=force
                )
                gemini_state["text"] = result["text"]
                gemini_state["for"] = result["for"]
                nonlocal gemini_fp, subject_zillow_url, peer_refs
                subject_zillow_url = result["subject_zillow_url"]
                peer_refs = result["peer_refs"]
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
                    ).props("unelevated dense color=dark")
                else:
                    label = "Regenerate" if text else "Ask Gemini"
                    ui.button(
                        label,
                        on_click=lambda: run_gemini(force=False),
                        icon="auto_awesome",
                    ).props("unelevated dense color=dark").classes("hb-btn-cta")

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
