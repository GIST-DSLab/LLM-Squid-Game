import sys, time; from env import prov
from concurrent.futures import ThreadPoolExecutor
def one(n):
    t=time.time()
    try:
        r=prov(n,300).complete([{"role":"system","content":"Reply briefly."},{"role":"user","content":"Say OK and your model family in 5 words."}],2000)
        return n, round(time.time()-t), r.text[:80], r.out_tokens, len(r.thinking)
    except Exception as e: return n, 'ERR', str(e)[:200]
with ThreadPoolExecutor(4) as ex:
    for x in ex.map(one, sys.argv[1:]): print(x)
