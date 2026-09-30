"""Run all of Phase 4:  python -m src.analysis.run

Writes outputs/tables/*.csv (one or more per section) and outputs/*.png (one
chart per section), and prints the headline numbers. No LLM calls.
Core roasters give the headline; all roasters are the robustness check.
"""
import pandas as pd

from src import config
from src.analysis import charts, data, hedonic, index, levers, pass_through, positioning

OUT = config.OUTPUTS_DIR
ROAST_LOSSES = [0.15, 0.18, 0.20]


def main() -> None:
    data.TABLES.mkdir(parents=True, exist_ok=True)
    v = data.load_variants()
    it = data.items(v)
    core = sorted(set(it[it.tier == "core"].roaster))
    index_roasters = sorted(set(it.roaster) - data.NO_INDEX)
    quarters = sorted(set(it.quarter))
    partial = set(data.PARTIAL)

    # 1. Price index
    idx = index.build(it, index_roasters)
    costs = data.cost_series(0.18)
    cidx = index.cost_index(costs)
    idx.to_csv(data.TABLES / "1_price_index.csv", index=False)
    cidx.to_csv(data.TABLES / "1_cost_index.csv", index=False)
    index.step_timing(idx, data.SHOCK_START).to_csv(data.TABLES / "1_step_timing.csv", index=False)
    charts.index_chart(idx, cidx, [r for r in core if r in index_roasters], quarters, partial,
                       OUT / "1_price_index.png")

    # 2. Pass-through, at three roast losses
    pts = [pass_through.pass_through(idx, it, data.cost_series(rl), rl) for rl in ROAST_LOSSES]
    pt_all = pd.concat(pts, ignore_index=True)
    pt_all.to_csv(data.TABLES / "2_pass_through_all.csv", index=False)
    heads = [pass_through.headline(p) for p in pts]
    head = heads[1].copy()                                   # 18% = the assumption
    for rl, h in zip(ROAST_LOSSES, heads):
        head[f"rupee_pt_at_{int(rl * 100)}pct_loss"] = h.set_index("roaster").loc[
            head.roaster, "rupee_pass_through_pct"].values
    head["partial"] = head.roaster.isin(partial)
    head.to_csv(data.TABLES / "2_pass_through_headline.csv", index=False)
    dl_core = pass_through.distributed_lag(idx, costs, [r for r in core if r in index_roasters])
    dl_all = pass_through.distributed_lag(idx, costs, index_roasters)
    pd.concat([dl_core["table"].assign(sample="core"), dl_all["table"].assign(sample="all")]) \
        .to_csv(data.TABLES / "2_distributed_lag.csv", index=False)
    charts.pass_through_chart(pts[1][pts[1].roaster.isin(core)], head[head.roaster.isin(core)],
                              partial, OUT / "2_pass_through.png")

    # 3. Levers
    cov = pd.read_csv(data.CLEAN / "coverage_report.csv", dtype=str)
    lev = levers.levers(it, v, cov, idx)
    lev.to_csv(data.TABLES / "3_levers.csv", index=False)
    levers.cut_table(v).to_csv(data.TABLES / "3_size_cuts.csv", index=False)
    charts.levers_chart(lev, OUT / "3_levers.png")

    # 4. Hedonic: core (headline) and all (robustness)
    out_res, out_counts, out_shift = [], [], []
    for name, roasters in (("core", core), ("all", sorted(set(it.roaster)))):
        res, counts, shift = hedonic.hedonic(it, roasters)
        out_res.append(res.assign(sample=name))
        out_counts.append(counts.assign(sample=name))
        out_shift.append(shift.assign(sample=name))
    res_all, counts_all = pd.concat(out_res), pd.concat(out_counts)
    res_all.to_csv(data.TABLES / "4_hedonic_coefficients.csv", index=False)
    counts_all.to_csv(data.TABLES / "4_hedonic_counts.csv", index=False)
    pd.concat(out_shift).to_csv(data.TABLES / "4_hedonic_shock_shifts.csv", index=False)
    rc = res_all[res_all["sample"] == "core"]
    note = (f"Core roasters. Before: {int(rc[rc.period == 'pre'].n_obs.iloc[0])} observations, "
            f"{int(rc[rc.period == 'pre'].n_products.iloc[0])} products; during: "
            f"{int(rc[rc.period == 'shock'].n_obs.iloc[0])} observations, "
            f"{int(rc[rc.period == 'shock'].n_products.iloc[0])} products. SEs clustered by product.")
    charts.hedonic_chart(rc, counts_all[counts_all["sample"] == "core"], OUT / "4_hedonic.png", note)

    # 5. Positioning
    pos = positioning.positioning(it, idx, lev)
    pos.to_csv(data.TABLES / "5_positioning.csv", index=False)
    end = head[head.quarter == data.END]
    charts.positioning_chart(pos, float(end.cost_change_pct.iloc[0]) if len(end) else float("nan"),
                             OUT / "5_positioning.png",
                             cost_change_rs=float(end.cost_change_rs.iloc[0]) if len(end) else None)

    # Robustness: CPI-deflated rupee pass-through (only if a CPI file is present)
    from src.analysis import inflation
    cpi_path = inflation.cpi_file()
    if cpi_path is None:
        print("NOTE: no India CPI file in data/external/ (name containing 'CPI'): "
              "inflation check skipped")
    else:
        monthly, splice_info = inflation.monthly_cpi(cpi_path)
        monthly.to_csv(data.TABLES / "2_cpi_monthly_spliced.csv", index=False)
        if splice_info:
            pd.DataFrame([splice_info]).to_csv(data.TABLES / "2_cpi_splice.csv", index=False)
            print("CPI splice:", splice_info)
        cpi_q = inflation.load_cpi(cpi_path)
        cpi_q.to_csv(data.TABLES / "2_cpi_quarterly.csv", index=False)
        real = inflation.deflate(head, cpi_q)
        real.to_csv(data.TABLES / "2_pass_through_real_cpi.csv", index=False)
        rc = real[real.roaster.isin(core)]
        print(f"CPI files: {[p.name for p in cpi_path]}")
        print("real rupee pass-through, core median:", rc.real_rupee_pass_through_pct.median(),
              "| points from inflation, core median:", rc.pass_through_from_inflation_pts.median())

    # Headline summary
    h_core = head[head.roaster.isin(core)]
    print("rupee pass-through, core median:", h_core.rupee_pass_through_pct.median(),
          "| core excl. partial:", h_core[~h_core.partial].rupee_pass_through_pct.median(),
          "| all index roasters:", head.rupee_pass_through_pct.median())
    print("percent pass-through, core median:", h_core.percent_pass_through_pct.median())
    print(f"wrote {len(list(data.TABLES.glob('*.csv')))} tables and 5 charts to {OUT}")


if __name__ == "__main__":
    main()
