"""Analysis as fixed in the approach: proportions with Wilson 95% intervals, exact two-sided McNemar tests on
paired units, Wilcoxon signed-rank tests on cell F1, Holm adjustment over the six pre-listed comparisons, and
bootstrap intervals clustered by task. No test is added after the run."""
from __future__ import annotations

import csv
import json
import math
import random
import shutil
from collections import defaultdict

from rh.util import RESULTS, RUNS, read_jsonl

from . import spec

Z = 1.959963984540054
DIRECTIONAL_BELOW = 12


def wilson(k: int, n: int) -> tuple:
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + Z * Z / n
    c = p + Z * Z / (2 * n)
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def wilcoxon(diffs: list) -> tuple:
    """Signed-rank test, zeros dropped, average ranks for ties, normal approximation with tie and continuity
    correction. Returns (n used, W+, p two-sided)."""
    d = [x for x in diffs if abs(x) > 1e-12]
    n = len(d)
    if n == 0:
        return (0, 0.0, 1.0)
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    tie_term = 0.0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(d[order[j + 1]]) - abs(d[order[i]])) < 1e-12:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        t = j - i + 1
        tie_term += t ** 3 - t
        i = j + 1
    wp = sum(r for r, x in zip(ranks, d) if x > 0)
    mu = n * (n + 1) / 4
    var = n * (n + 1) * (2 * n + 1) / 24 - tie_term / 48
    if var <= 0:
        return (n, wp, 1.0)
    z = (abs(wp - mu) - 0.5) / math.sqrt(var)
    p = math.erfc(max(z, 0.0) / math.sqrt(2))
    return (n, wp, min(1.0, p))


def holm(ps: list) -> list:
    idx = sorted(range(len(ps)), key=lambda i: ps[i])
    out = [None] * len(ps)
    run = 0.0
    m = len(ps)
    for rank, i in enumerate(idx):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        out[i] = run
    return out


def cluster_bootstrap(rows: list, value, cluster, b: int = 2000, seed: int = 20261116) -> tuple:
    """Percentile interval of a mean, resampling whole clusters (tasks)."""
    groups = defaultdict(list)
    for r in rows:
        groups[cluster(r)].append(value(r))
    keys = sorted(groups)
    if not keys:
        return (None, None)
    rng = random.Random(seed)
    means = []
    for _ in range(b):
        tot = cnt = 0
        for _k in keys:
            g = groups[keys[rng.randrange(len(keys))]]
            tot += sum(g)
            cnt += len(g)
        means.append(tot / cnt if cnt else 0.0)
    means.sort()
    return (means[int(0.025 * b)], means[min(b - 1, int(0.975 * b))])


def _f(x, nd=4):
    return "" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def _write(name: str, header: list, rows: list) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([_f(x) for x in r])


def _rate(rows, pred):
    k = sum(1 for r in rows if pred(r))
    lo, hi = wilson(k, len(rows))
    return [len(rows), k, (k / len(rows)) if rows else None, lo, hi]


def _paired(rows_a: dict, rows_b: dict, label: str) -> dict:
    """a and b are {pair key: final row}; b is the comparison's second member (tested as b minus a)."""
    keys = sorted(set(rows_a) & set(rows_b))
    b = sum(1 for k in keys if rows_a[k]["final"].get("exact") and not rows_b[k]["final"].get("exact"))
    c = sum(1 for k in keys if not rows_a[k]["final"].get("exact") and rows_b[k]["final"].get("exact"))
    diffs = [(rows_b[k]["final"].get("f1") or 0.0) - (rows_a[k]["final"].get("f1") or 0.0) for k in keys]
    n_w, wp, p_w = wilcoxon(diffs)
    return {"comparison": label, "pairs": len(keys), "first_only_exact": b, "second_only_exact": c,
            "mcnemar_p": mcnemar_exact(b, c), "directional_only": (b + c) < DIRECTIONAL_BELOW,
            "wilcoxon_n": n_w, "wilcoxon_w_plus": wp, "wilcoxon_p": p_w,
            "mean_f1_diff": (sum(diffs) / len(diffs)) if diffs else None,
            "build_pass_first": sum(1 for k in keys if rows_a[k]["final"].get("build_ok")),
            "build_pass_second": sum(1 for k in keys if rows_b[k]["final"].get("build_ok"))}


def comparisons(rows: list) -> list:
    stg = [r for r in rows if r["kind"] == "stg"]

    def by_arm(arm):
        return {(r["task"], r["model"], r["sample"]): r for r in rows if r["arm"] == arm}

    def by_fmt(fmt):
        return {(r["target"], r["model"], r["arm"], r["sample"]): r for r in stg if r["format"] == fmt}

    out = [_paired(by_arm("A1"), by_arm("A2"), "A2 vs A1"), _paired(by_arm("A2"), by_arm("A3"), "A3 vs A2"),
           _paired(by_fmt("fhir_stu3"), by_fmt("fhir_r4"), "R4 vs STU3"),
           _paired(by_fmt("claims"), by_fmt("fhir_r4"), "R4 vs claims"),
           _paired(by_fmt("d2"), by_fmt("d1"), "dialect 1 vs 2"), _paired(by_fmt("d3"), by_fmt("d2"), "dialect 2 vs 3")]
    for key in ("mcnemar_p", "wilcoxon_p"):
        adj = holm([o[key] for o in out])
        for o, a in zip(out, adj):
            o[key + "_holm"] = a
    return out


def run(ctx) -> None:
    rows = list(read_jsonl(RUNS / "full" / "final.jsonl"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    fin = lambda r: r["final"]  # noqa: E731
    # ---- per cell
    _write("cells.csv", ["task", "kind", "format", "target", "arm", "sample", "model", "turns", "build_ok", "tests_ok",
                         "exact", "silent_wrong", "precision", "recall", "f1", "recoverable_cells", "correct_cells",
                         "extra_rows", "content_stable", "key_stable", "existing_undisturbed", "new_columns_ok", "no_sql",
                         "eval_error", "first_turn_build_ok", "first_turn_exact"],
           [[r["task"], r["kind"], r["format"], r["target"], r["arm"], r["sample"], r["model"], r["turns"],
             fin(r).get("build_ok"), fin(r).get("tests_ok"), fin(r).get("exact"), fin(r).get("silent_wrong"),
             fin(r).get("precision"), fin(r).get("recall"), fin(r).get("f1"), fin(r).get("recoverable_cells"),
             fin(r).get("correct_cells"), fin(r).get("extra_rows"), fin(r).get("content_stable"), fin(r).get("key_stable"),
             (fin(r).get("wide") or {}).get("existing_undisturbed"), (fin(r).get("wide") or {}).get("new_columns_ok"),
             fin(r).get("no_sql"), fin(r).get("eval_error"), r["by_turn"][0].get("build_ok"), r["by_turn"][0].get("exact")]
            for r in rows])
    # ---- RQ1: correctness by format and domain, per model and arm
    t1 = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["kind"], r["format"], r["target"], r["model"], r["arm"])].append(r)
        groups[(r["kind"], r["format"], "(all)", r["model"], r["arm"])].append(r)
        groups[(r["kind"], r["format"], "(all)", "(all)", r["arm"])].append(r)
        groups[(r["kind"], r["format"], "(all)", "(all)", "(all)")].append(r)
    for k, g in sorted(groups.items()):
        f1s = [fin(r).get("f1") or 0.0 for r in g]
        lo, hi = cluster_bootstrap(g, lambda r: 1.0 if fin(r).get("exact") else 0.0, lambda r: r["task"])
        t1.append([*k, *_rate(g, lambda r: fin(r).get("exact")), lo, hi, sum(f1s) / len(f1s),
                   sum(1 for r in g if fin(r).get("build_ok")), sum(1 for r in g if fin(r).get("tests_ok"))])
    _write("t1_correctness.csv", ["kind", "format", "target", "model", "arm", "n", "exact", "exact_share", "wilson_lo",
                                  "wilson_hi", "task_bootstrap_lo", "task_bootstrap_hi", "mean_f1", "build_pass", "tests_pass"], t1)
    # ---- RQ2: silent wrong among integrations that pass build and tests
    t2 = []
    groups = defaultdict(list)
    for r in rows:
        if fin(r).get("build_ok") and fin(r).get("tests_ok"):
            for k in ((r["kind"], r["model"], r["arm"]), (r["kind"], r["model"], "(all)"), (r["kind"], "(all)", r["arm"]),
                      (r["kind"], "(all)", "(all)"), ("(all)", "(all)", "(all)")):
                groups[k].append(r)
    for k, g in sorted(groups.items()):
        t2.append([*k, *_rate(g, lambda r: not fin(r).get("exact"))])
    _write("t2_silent_wrong.csv", ["kind", "model", "arm", "passing_build_and_tests", "wrong", "wrong_share", "wilson_lo", "wilson_hi"], t2)
    # ---- RQ3: non-regression
    t3 = []
    built = [r for r in rows if fin(r).get("build_ok") and r["kind"] == "stg"]
    groups = defaultdict(list)
    for r in built:
        groups[("integration", r["format"])].append(r)
        groups[("integration", "(all)")].append(r)
    for (scope, f), g in sorted(groups.items()):
        c = _rate(g, lambda r: fin(r).get("content_stable"))
        k = _rate(g, lambda r: fin(r).get("key_stable"))
        t3.append([scope, f, "", c[0], c[1], c[2], c[3], c[4], k[1], k[2], k[3], k[4]])
    st = {}
    try:
        st = json.loads((RUNS / "prepare" / "state.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    for t, c in sorted(((st.get("steps") or {}).get("controls") or {}).get("info", {}).items()):
        t3.append(["control", "rebuild of the pre-acquisition pipeline", t, c["acquirer_rows"], c["rebuild_content_diff_rows"], "", "", "",
                   c["rebuild_keys_equal"], "", "", ""])
        t3.append(["control", "gold build against the pre-acquisition pipeline", t, c["acquirer_rows"], c["gold_content_diff_rows"], "", "", "",
                   c["gold_keys_equal"], "", "", ""])
    _write("t3_non_regression.csv", ["scope", "format_or_control", "table", "n_or_rows", "content_stable_or_diff_rows",
                                     "content_stable_share", "wilson_lo", "wilson_hi", "key_stable_or_keys_equal",
                                     "key_stable_share", "key_wilson_lo", "key_wilson_hi"], t3)
    # ---- RQ4: wide contract
    t4 = []
    groups = defaultdict(list)
    for r in rows:
        if r["kind"] == "wide" and fin(r).get("build_ok") and fin(r).get("wide"):
            for k in ((r["target"], r["format"], r["model"], r["arm"]), (r["target"], r["format"], "(all)", "(all)"),
                      ("(all)", "(all)", r["model"], r["arm"]), ("(all)", "(all)", "(all)", "(all)")):
                groups[k].append(r)
    for k, g in sorted(groups.items()):
        d = _rate(g, lambda r: not fin(r)["wide"]["existing_undisturbed"])
        nw = _rate(g, lambda r: fin(r)["wide"]["new_columns_ok"])
        t4.append([*k, d[0], d[1], d[2], d[3], d[4], nw[1], nw[2], sum(1 for r in g if fin(r).get("exact"))])
    _write("t4_wide_contract.csv", ["product", "family", "model", "arm", "built", "existing_disturbed", "disturbed_share",
                                    "wilson_lo", "wilson_hi", "new_columns_present", "new_columns_share", "exact"], t4)
    # ---- RQ5: arms, first turn against final turn
    t5 = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["arm"], r["model"])].append(r)
        groups[(r["arm"], "(all)")].append(r)
    for (arm, m), g in sorted(groups.items()):
        t5.append([arm, m, len(g), sum(1 for r in g if r["by_turn"][0].get("build_ok")),
                   sum(1 for r in g if fin(r).get("build_ok")), sum(1 for r in g if r["by_turn"][0].get("tests_ok")),
                   sum(1 for r in g if fin(r).get("tests_ok")), sum(1 for r in g if r["by_turn"][0].get("exact")),
                   sum(1 for r in g if fin(r).get("exact")), sum(fin(r).get("f1") or 0.0 for r in g) / len(g),
                   sum(r["turns"] for r in g) / len(g)])
    _write("t5_arms.csv", ["arm", "model", "n", "build_pass_turn1", "build_pass_final", "tests_pass_turn1", "tests_pass_final",
                           "exact_turn1", "exact_final", "mean_f1_final", "mean_turns"], t5)
    comp = comparisons(rows)
    _write("t6_comparisons.csv", list(comp[0].keys()), [list(c.values()) for c in comp])
    # ---- hypotheses, stated as counts; no verdict is forced
    passing = [r for r in rows if fin(r).get("build_ok") and fin(r).get("tests_ok")]
    wides = [r for r in rows if r["kind"] == "wide" and fin(r).get("build_ok") and fin(r).get("wide")]
    cmap = {c["comparison"]: c for c in comp}
    a1 = [r for r in rows if r["arm"] == "A1"]
    a2 = [r for r in rows if r["arm"] == "A2"]
    hyp = [
        ["H1", "share wrong among integrations passing build and all tests", len(passing), sum(1 for r in passing if not fin(r).get("exact"))],
        ["H2", "exact: R4 vs STU3 (first only / second only)", cmap["R4 vs STU3"]["pairs"],
         f"{cmap['R4 vs STU3']['first_only_exact']}/{cmap['R4 vs STU3']['second_only_exact']}"],
        ["H2", "exact: R4 vs claims (first only / second only)", cmap["R4 vs claims"]["pairs"],
         f"{cmap['R4 vs claims']['first_only_exact']}/{cmap['R4 vs claims']['second_only_exact']}"],
        ["H3", "exact: dialect 1 vs 2 (first only / second only)", cmap["dialect 1 vs 2"]["pairs"],
         f"{cmap['dialect 1 vs 2']['first_only_exact']}/{cmap['dialect 1 vs 2']['second_only_exact']}"],
        ["H3", "exact: dialect 2 vs 3 (first only / second only)", cmap["dialect 2 vs 3"]["pairs"],
         f"{cmap['dialect 2 vs 3']['first_only_exact']}/{cmap['dialect 2 vs 3']['second_only_exact']}"],
        ["H4", "build pass A1 -> A2 (count of n)", len(a1), f"{sum(1 for r in a1 if fin(r).get('build_ok'))} -> {sum(1 for r in a2 if fin(r).get('build_ok'))}"],
        ["H4", "exact A1 -> A2 (count of n)", len(a1), f"{sum(1 for r in a1 if fin(r).get('exact'))} -> {sum(1 for r in a2 if fin(r).get('exact'))}"],
        ["H5", "built staging integrations with content of existing rows stable", len(built), sum(1 for r in built if fin(r).get("content_stable"))],
        ["H5", "built staging integrations with generated keys of existing rows stable", len(built), sum(1 for r in built if fin(r).get("key_stable"))],
        ["H6", "built wide extensions that disturb an existing column", len(wides), sum(1 for r in wides if not fin(r)["wide"]["existing_undisturbed"])],
        ["H7", "exact: A3 vs A2 (first only / second only), two-sided", cmap["A3 vs A2"]["pairs"],
         f"{cmap['A3 vs A2']['first_only_exact']}/{cmap['A3 vs A2']['second_only_exact']}"],
    ]
    _write("hypotheses.csv", ["hypothesis", "quantity", "n", "count"], hyp)
    # ---- provenance
    if (RUNS / "prepare").exists():
        shutil.copytree(RUNS / "prepare", RESULTS / "prepare", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("population.tar.gz", "*.part"))   # the archive stays in runs/ only
    if (RUNS / "decisions.md").exists():
        shutil.copyfile(RUNS / "decisions.md", RESULTS / "decisions.md")
