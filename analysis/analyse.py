"""Recomputes every number quoted in the paper from the run records.

Usage: python3 analyse.py <folder that holds runs/> [output.json]   (default output: numbers.json)
Reads runs/full/final.jsonl, runs/full/eval0.jsonl, eval1.jsonl, eval2.jsonl and runs/ledger.jsonl.
"""
import json,csv,collections,math,random,statistics as st
from math import comb
import sys
P=(sys.argv[1] if len(sys.argv)>1 else '.').rstrip('/')+'/'   # folder of the pulled run (holds runs/ and results/)
F=[json.loads(l) for l in open(P+'runs/full/final.jsonl')]
ev={}
for fn in ('eval0','eval1','eval2'):
    for l in open(P+f'runs/full/{fn}.jsonl'):
        r=json.loads(l); ev[(r['base'],r['turn'])]=r
DEF={'build_ok':False,'tests_ok':False,'exact':False,'f1':0.0,'content_stable':False,'key_stable':False,'extra_rows':0,'recoverable_cells':0,'correct_cells':0}
for f in F:
    for k,v in DEF.items(): f['final'].setdefault(k,v)
for r in ev.values():
    for k,v in DEF.items(): r['result'].setdefault(k,v)
def wilson(k,n,z=1.959964):
    if n==0: return (0,0)
    p=k/n; d=1+z*z/n; c=p+z*z/(2*n); h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return ((c-h)/d,(c+h)/d)
def mcnemar(b,c):
    n=b+c
    if n==0: return 1.0
    k=min(b,c); p=sum(comb(n,i) for i in range(k+1))/2**n*2
    return min(1.0,p)
def cls(x):
    return 'nobuild' if not x['build_ok'] else 'testfail' if not x['tests_ok'] else 'silent' if not x['exact'] else 'exact'
O={}
stg=[f for f in F if f['kind']=='stg']; wide=[f for f in F if f['kind']=='wide']
O['n']={'all':len(F),'stg':len(stg),'wide':len(wide),'tasks_stg':len({f['task'] for f in stg}),'tasks_wide':len({f['task'] for f in wide})}
O['stg_tot']={'built':sum(f['final']['build_ok'] for f in stg),'exact':sum(f['final']['exact'] for f in stg),'tests':sum(f['final']['tests_ok'] for f in stg)}
# format x arm
fa={}
for fmt in ('fhir_r4','fhir_stu3','claims','d1','d2','d3'):
    for arm in ('A1','A2','A3'):
        s=[f for f in stg if f['format']==fmt and f['arm']==arm]
        k=sum(f['final']['exact'] for f in s); lo,hi=wilson(k,len(s))
        cc=collections.Counter(cls(f['final']) for f in s)
        fa[f'{fmt}|{arm}']={'n':len(s),'exact':k,'lo':round(lo*100,1),'hi':round(hi*100,1),'build':sum(f['final']['build_ok'] for f in s),'tests':sum(f['final']['tests_ok'] for f in s),'silent':cc['silent'],'meanf1':round(st.mean(f['final']['f1'] for f in s),3)}
    s=[f for f in stg if f['format']==fmt]; k=sum(f['final']['exact'] for f in s)
    fa[f'{fmt}|all']={'n':len(s),'exact':k,'tasks':len({f['task'] for f in s})}
O['format_arm']=fa
# model x arm (staging)
ma={}
for m in ('claude-sonnet-5-5','gpt-6.1-sol','openai/gpt-oss-120b'):
    for arm in ('A1','A2','A3','all'):
        s=[f for f in stg if f['model']==m and (arm=='all' or f['arm']==arm)]
        cc=collections.Counter(cls(f['final']) for f in s)
        passing=cc['silent']+cc['exact']; lo,hi=wilson(cc['silent'],passing)
        ex=sum(f['final']['exact'] for f in s)
        ma[f'{m}|{arm}']={'n':len(s),'build':sum(f['final']['build_ok'] for f in s),'tests':passing,'exact':ex,'silent':cc['silent'],'sw_share':round(100*cc['silent']/passing,1),'sw_lo':round(lo*100,1),'sw_hi':round(hi*100,1),'turns':round(st.mean(f['turns'] for f in s),2),'exact_pct':round(100*ex/len(s),1)}
O['model_arm']=ma
# arm totals staging
aa={}
for arm in ('A1','A2','A3','all'):
    s=[f for f in stg if (arm=='all' or f['arm']==arm)]
    cc=collections.Counter(cls(f['final']) for f in s); passing=cc['silent']+cc['exact']; lo,hi=wilson(cc['silent'],passing)
    ex=sum(f['final']['exact'] for f in s); elo,ehi=wilson(ex,len(s))
    aa[arm]={'n':len(s),**cc,'passing':passing,'sw_share':round(100*cc['silent']/passing,1),'sw_lo':round(lo*100,1),'sw_hi':round(hi*100,1),'exact_all':ex,'exact_pct':round(100*ex/len(s),1),'exact_lo':round(elo*100,1),'exact_hi':round(ehi*100,1),'build':sum(f['final']['build_ok'] for f in s)}
O['arm_stg']=aa
# bootstrap by task for silent-wrong share (stg, all arms)
random.seed(20261117)
tasks=sorted({f['task'] for f in stg}); bt=collections.defaultdict(list)
for f in stg: bt[f['task']].append(cls(f['final']))
vals=[]
for _ in range(5000):
    sm=[random.choice(tasks) for _ in tasks]; s=p=0
    for t in sm:
        s+=bt[t].count('silent'); p+=bt[t].count('silent')+bt[t].count('exact')
    vals.append(s/p)
vals.sort(); O['sw_boot']=[round(100*vals[125],1),round(100*vals[4874],1)]
O['sw_tasks']={'tasks_with_any':len({f['task'] for f in stg if cls(f['final'])=='silent'}),'tasks':len(tasks)}
# pairs
def key(f,drop): return tuple(v for k,v in (('task',f['task']),('arm',f['arm']),('model',f['model']),('sample',f['sample'])) if k not in drop)
def pair(A,B,drop):
    da={key(f,drop):f for f in A}; db={key(f,drop):f for f in B}
    ks=sorted(set(da)&set(db)); a=sum(da[k]['final']['exact'] and not db[k]['final']['exact'] for k in ks); b=sum(db[k]['final']['exact'] and not da[k]['final']['exact'] for k in ks)
    return {'pairs':len(ks),'first_only':a,'second_only':b,'p':mcnemar(a,b),'exact_first':sum(da[k]['final']['exact'] for k in ks),'exact_second':sum(db[k]['final']['exact'] for k in ks),'build_first':sum(da[k]['final']['build_ok'] for k in ks),'build_second':sum(db[k]['final']['build_ok'] for k in ks)}
arm=lambda S,a:[f for f in S if f['arm']==a]
PR={}
PR['A2 vs A1 (all)']=pair(arm(F,'A2'),arm(F,'A1'),{'arm'})
PR['A3 vs A2 (all)']=pair(arm(F,'A3'),arm(F,'A2'),{'arm'})
PR['A2 vs A1 (stg)']=pair(arm(stg,'A2'),arm(stg,'A1'),{'arm'})
PR['A3 vs A2 (stg)']=pair(arm(stg,'A3'),arm(stg,'A2'),{'arm'})
def fmtpair(a,b):
    A=[dict(f,task=f['target']) for f in stg if f['format']==a]; B=[dict(f,task=f['target']) for f in stg if f['format']==b]
    return pair(A,B,set())
PR['R4 vs STU3']=fmtpair('fhir_r4','fhir_stu3'); PR['R4 vs claims']=fmtpair('fhir_r4','claims')
PR['d1 vs d2']=fmtpair('d1','d2'); PR['d2 vs d3']=fmtpair('d2','d3')
# Holm over the six pre-listed (all-cells versions for arms)
six=['A2 vs A1 (all)','A3 vs A2 (all)','R4 vs STU3','R4 vs claims','d1 vs d2','d2 vs d3']
order=sorted(six,key=lambda k:PR[k]['p']); prev=0
for i,k in enumerate(order):
    adj=min(1.0,PR[k]['p']*(len(six)-i)); adj=max(adj,prev); prev=adj; PR[k]['p_holm']=adj
O['pairs']=PR
# silent wrong severity
sw=[f for f in stg if cls(f['final'])=='silent']
sh=[(f['final']['recoverable_cells']-f['final']['correct_cells'])/f['final']['recoverable_cells'] for f in sw]
O['sw_sev']={'n':len(sw),'median_pct':round(100*st.median(sh),2),'lt1pct':sum(x<0.01 for x in sh),'ge10pct':sum(x>=0.10 for x in sh),'ge50pct':sum(x>=0.5 for x in sh),'min_cells':min(f['final']['recoverable_cells']-f['final']['correct_cells'] for f in sw),'with_extra_rows':sum(f['final']['extra_rows']>0 for f in sw)}
O['sw_by_target']=collections.Counter(f['target'] for f in sw).most_common()
O['sw_by_format']=collections.Counter(f['format'] for f in sw).most_common()
# repair trajectories
rep={}
for a in ('A2','A3'):
    s=[f for f in stg if f['arm']==a]
    need=[f for f in s if ev[(f['base'],0)]['needs_repair']]
    first=collections.Counter(cls(ev[(f['base'],0)]['result']) for f in s)
    fin=collections.Counter(cls(f['final']) for f in need)
    rep[a]={'n':len(s),'first':dict(first),'needed_repair':len(need),'after':dict(fin),'turn_hist':dict(collections.Counter(f['turns'] for f in s))}
    # first-turn silent wrong remain?
    rep[a]['first_silent_final']=dict(collections.Counter(cls(f['final']) for f in s if cls(ev[(f['base'],0)]['result'])=='silent'))
    rep[a]['first_exact_testfail']=sum(1 for f in s if ev[(f['base'],0)]['result']['exact'] and not ev[(f['base'],0)]['result']['tests_ok'])
O['repair']=rep
O['needs_repair_rule_check']=collections.Counter((cls(r['result']),r['needs_repair']) for (b,t),r in ev.items() if t==0 and r['meta']['arm']!='A1' and r['meta']['kind']=='stg').most_common()
# exact but tests fail
O['exact_testfail']=collections.Counter((f['format'],f['target'],f['arm']) for f in stg if f['final']['exact'] and not f['final']['tests_ok']).most_common()
# key / content
O['keys']={'built':sum(f['final']['build_ok'] for f in stg),'content_stable':sum(1 for f in stg if f['final']['build_ok'] and f['final']['content_stable']),'key_stable':sum(1 for f in stg if f['final']['build_ok'] and f['final']['key_stable'])}
# wide
O['wide']={'n':len(wide),'exact':sum(f['final']['exact'] for f in wide),'first_turn_exact':sum(ev[(f['base'],0)]['result']['exact'] for f in wide),'turns1':sum(f['turns']==1 for f in wide)}
# time per candidate
secs=[r['result']['seconds'] for r in ev.values() if 'seconds' in r['result']]; O['eval_seconds']={'n':len(secs),'median':st.median(secs),'p90':sorted(secs)[int(.9*len(secs))]}
# recoverable cells
O['cells']={'stg_recoverable_median':st.median(f['final']['recoverable_cells'] for f in stg if f['final']['build_ok']),'min':min(f['final']['recoverable_cells'] for f in stg if f['final']['build_ok']),'max':max(f['final']['recoverable_cells'] for f in stg)}
# ledger tokens
L=[json.loads(l) for l in open(P+'runs/ledger.jsonl')]
O['ledger_keys']=sorted(L[0].keys())
OUT=sys.argv[2] if len(sys.argv)>2 else 'numbers.json'
with open(OUT,'w') as f:
    json.dump(O,f,indent=1,default=str)
print('wrote',OUT)
