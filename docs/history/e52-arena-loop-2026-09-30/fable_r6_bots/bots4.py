import bots3_mod as b, statistics as st, random
def run(focal, mult, N=8000, **kw):
    res = [b.session(focal, int(mult*(b.P+b.S)), random.Random(i), **kw) for i in range(N)]
    return [r for r,_,_ in res], st.mean(a for _,a,_ in res)
for D in (250, 600, 1000):
    b.D = D
    for kw in ({}, {"show_p":0.85}):
        for mult in (4, 3, 2.5):
            a, aa = run("answer_always", mult, **kw); d, da = run("decline_poor", mult, **kw)
            diff = [y-x for x,y in zip(a,d)]
            rng = random.Random(1); n = len(diff)
            boots = sorted(st.mean(rng.choices(diff, k=n)) for _ in range(300))
            print(f"decline cost {D:>4} {str(kw):<18} start {mult}c: always {st.mean(a):.2f} (open {aa:.2f})  decline {st.mean(d):.2f} (open {da:.2f})  diff {st.mean(diff):+.2f} [{boots[7]:+.2f},{boots[292]:+.2f}]")
