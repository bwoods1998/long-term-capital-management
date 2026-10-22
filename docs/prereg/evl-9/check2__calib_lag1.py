"""calib_lag1.py -- SYNTHETIC ONLY (adversarial check #2 of PREREG-EVL-9). The judge's paths and screen
(evl9/judge/calib_evl9_final.py: the learners lens's generator and warm learner, PREREG-EVL-6's final rule), imported
unchanged, re-run at TRAINING LAG 1 beside lag 2 on fresh seeds. EVL-WL-O1 enters at D's open and exits at D's close; its
pool outcomes settle the same night and train the next morning's decision: its real lag is 1. The draft's figures are
all at the module default lag 2. No real data of any kind is read."""
import dataclasses, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))
import calib_evl9_final as jf  # noqa: E402

W, WN = jf.W, jf.WN
C = lambda *a, **k: jf.WCell(*a, **({"nbar": 300.0} | k))  # noqa: E731


def cells():
    out = []
    for lag in (1,):
        out += [
            C(f"CHAR20-HD08-worst-lag{lag}", ic_h=0.08, drift_c=0.0020, lag=lag, **W),
            C(f"CHAR20-HD08-worst-notau-phi20-lag{lag}", ic_h=0.08, drift_c=0.0020, lag=lag, **(WN | dict(phi_day=0.20))),
            C(f"N1-H0-worst-lag{lag}", ic_h=0.0, lag=lag, **W),
            C(f"N1-HD08-worst-phi20-lag{lag}", ic_h=0.08, lag=lag, **(W | dict(phi_day=0.20))),
        ]
    return out


def main(reps=1000, chunk=50, workers=4):
    from multiprocessing import Pool
    cs = cells()
    seed0 = 197_000_001
    jobs = [(cell, seed0 + 1000 * ci + j, chunk) for ci, cell in enumerate(cs) for j in range(reps // chunk)]
    jf.cw.population()
    agg = {}
    t0 = time.time()
    with Pool(workers) as pool:
        for k, res in enumerate(pool.imap_unordered(jf._job, jobs)):
            a = agg.setdefault(res["cell"], {"n": 0, "p1": 0, "pv": 0})
            a["n"] += res["R"]; a["p1"] += sum(res["ev6f"]["p1"]); a["pv"] += sum(res["ev6f"]["pv"])
            if (k + 1) % 20 == 0:
                print(f"{k + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    out = {}
    for name, a in sorted(agg.items()):
        p = a["p1"] / a["n"]
        out[name] = {"R": a["n"], "run1": round(p, 4), "se": round((p * (1 - p) / a["n"]) ** 0.5, 4),
                     "either_run_120": round(a["pv"] / a["n"], 4)}
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(HERE, "calib_lag1.out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
