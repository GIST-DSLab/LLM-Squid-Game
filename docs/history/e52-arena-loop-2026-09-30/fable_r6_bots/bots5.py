import bots3_mod as b, statistics as st, random
b.D = 0
def run(focal, mult, N=8000, **kw):
    res = [b.session(focal, int(mult*(b.P+b.S)), random.Random(i), **kw) for i in range(N)]
    return [r for r,_,_ in res], st.mean(a for _,a,_ in res)
def ci(diff):
    rng = random.Random(1); n = len(diff)
    boots = sorted(st.mean(rng.choices(diff, k=n)) for _ in range(300))
    return boots[7], boots[292]
for kw in ({}, {"show_p":0.85}, {"show_p":0.5}, {"a_miss":0.45}, {"show_p":0.85,"a_miss":0.45}):
    print("\n###", kw or "base: show_p .7, persist .8, q 0.6c, f 1.2c, a .85/.30")
    for mult in (16, 6, 4, 3, 2.5, 2, 1.5):
        a, aa = run("answer_always", mult, **kw)
        f_, fa = run("rest_forecast", mult, **kw)
        d, da = run("decline_poor", mult, **kw)
        t, ta = run("decline_thin", mult, **kw)
        dd = [y-x for x,y in zip(a,d)]; lo,hi = ci(dd)
        print(f"  {mult:>4}c  SOLVE_IF 0: {st.mean(a):.2f} (open {aa:.2f}) | forecast rest: {st.mean(f_):.2f} ({fa:.2f}) | SOLVE_IF 3: {st.mean(d):.2f} ({da:.2f}) diff {st.mean(dd):+.2f} [{lo:+.2f},{hi:+.2f}] | 3 only when thin: {st.mean(t):.2f} ({ta:.2f})")
