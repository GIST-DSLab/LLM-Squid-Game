"""Manuscript figure from verified v33/v33ab 200-game opportunity summaries.

Input: result/2026-11-07/aid_opportunities_200games/summary.json.
The underlying frozen cohort is prize_robustness_20261105.json; no new analysis.
"""
import json
import sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

source,out=map(Path,sys.argv[1:3]);out.mkdir(parents=True,exist_ok=True)
s=json.loads(source.read_text())
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,'ps.fonttype':42,
                     'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(9.2,3.35),gridspec_kw={'width_ratios':[1.2,1]})
colors=['#267c86','#97bdb9','#b86b58']
for y,key in enumerate(['primary','exposure_sensitivity']):
    d=s[key];values=[d['supported'],d['delayed'],d['no_aid_from_first_opportunity']];left=0
    for value,color in zip(values,colors):
        width=100*value/d['n'];axes[0].barh(y,width,left=left,color=color,height=.48)
        axes[0].text(left+width/2,y,str(value),ha='center',va='center',color='white',fontweight='bold');left+=width
axes[0].set(yticks=[0,1],yticklabels=['Current-round ASK\n(n=77)','Post-results ASK\n(n=60)'],xlim=(0,100),
            xlabel='Eligible opportunities (%)',title='(a) Timing of executed aid')
axes[0].invert_yaxis()
axes[0].legend([plt.Rectangle((0,0),1,1,color=c) for c in colors],['Immediate','Later','None thereafter'],
               loc='upper center',bbox_to_anchor=(.5,-.24),ncol=3,frameon=False,fontsize=8)
for x,key in enumerate(['0_to_1','1_to_2','2_plus']):
    d=s['by_reserve'][key];v=100*d['rate'];lo,hi=np.array(d['ci95_seed_block'])*100
    axes[1].errorbar(x,v,yerr=[[v-lo],[hi-v]],fmt='o',color=colors[0],capsize=4,markersize=6)
    axes[1].text(x,v+6,f"{d['supported']}/{d['n']}",ha='center',fontsize=9)
axes[1].set(xticks=range(3),xticklabels=['0 to <1','1 to <2','2 or more'],ylim=(0,100),xlim=(-.45,2.45),
            ylabel='Immediate GIVE (%)',xlabel='Reserve after aid / current fine',title='(b) Reserve and immediate aid')
fig.tight_layout(w_pad=2)
for ext in ['pdf','png']:
    fig.savefig(out/f'aid_opportunities.{ext}',dpi=250,bbox_inches='tight')
plt.close(fig)
