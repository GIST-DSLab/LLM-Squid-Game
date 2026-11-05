import json,sys,glob
for d in sorted(glob.glob(sys.argv[1])):
    print("==", d)
    rows=[json.loads(l) for l in open(d+'/results.jsonl')]
    print(len(rows), "rows; format errors", sum(r['moved'] is None for r in rows))
    for r in sorted(rows,key=lambda r:(r['arm'],r['frame'],-r['giver'],r['rep'])):
        print(r['arm'][:3],r['frame'][:5],r['giver'],'moved',r['moved'],'out',r['out_tokens'],'|',(r['reason'] or r.get('format_error') or '')[:120])
