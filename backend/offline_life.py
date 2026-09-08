"""Choice-only life and authored local stories on the current adventure engine.

This module does not replace the atlas, battle engine, membership ledger,
property economy, mastery paths, or calendar. Its actions use their normal
signed preview/confirmation and request-receipt transaction.
"""
import copy
import hashlib
from systems import currency_balance, record_currency_transaction
from worlds import expansion_for

FLAVOR = {
 'One Piece': ('Mara Reef','navigator',('Unload harbor cargo','Repair fishing nets','Chart coastal currents','Prepare galley meals'),
   'The Harbor Levy', 'An unofficial levy is keeping small fishing crews ashore.',
   ('Audit the collector’s receipts','Help crews pool their supplies'),
   ('Present the evidence publicly','Negotiate a lower levy privately'),
   ('Fund an independent landing','Organize an accountable harbor council')),
 'Naruto': ('Ren Mizuno','field medic',('Deliver civilian messages','Maintain training targets','Assist the clinic','Survey public footpaths'),
   'Orders at the Border', 'A border settlement receives contradictory evacuation orders.',
   ('Verify the messenger’s route','Help families prepare to evacuate'),
   ('Report the forged order to village officials','Escort civilians before the dispute is settled'),
   ('Establish a permanent aid station','Train a local warning network')),
 'Bleach': ('Aya Mori','patrol specialist',('Repair district shelters','Distribute relief supplies','Maintain practice grounds','Assist a district courier'),
   'The Uncounted District', 'Relief records omit households on the district outskirts.',
   ('Count the missing households','Share your work with the relief queue'),
   ('Challenge the distribution record','Arrange a volunteer delivery line'),
   ('Build a community refuge','Keep a public distribution register')),
 'Hunter x Hunter': ('Tavi Rook','tracker',('Catalog expedition supplies','Appraise ordinary goods','Guide local travelers','Record wildlife observations'),
   'The False Provenance', 'An expedition sponsor is selling objects with conflicting ownership records.',
   ('Compare the provenance records','Interview the expedition workers'),
   ('Expose the disputed sale','Negotiate restitution to the workers'),
   ('Support an independent survey','Create a shared evidence archive')),
 'Jujutsu Kaisen': ('Nao Fujita','field assistant',('Check evacuation signs','Sort equipment','Deliver civilian supplies','Maintain a practice site'),
   'The Evacuation Gap', 'A civilian evacuation plan leaves an occupied apartment block behind.',
   ('Verify who is still inside','Prepare an accessible escape route'),
   ('Demand a revised evacuation boundary','Guide residents out before the next closure'),
   ('Fund a neighborhood safe room','Organize a civilian warning chain')),
 'Overgeared': ('Lysa Anvil','craftsperson',('Sort workshop stock','Repair ordinary fittings','Prepare guild supplies','Deliver merchant orders'),
   'The Workshop Contract', 'A workshop’s apprentices are locked into an unfair materials contract.',
   ('Audit the contract and invoices','Help apprentices meet their current quota'),
   ('Challenge the supplier through the guild','Arrange an alternative supply agreement'),
   ('Equip a cooperative workroom','Publish a fair-contract standard')),
 'Solo Max-Level Newbie': ('Min Seo','route scout',('Organize camp supplies','Mark verified routes','Maintain shelters','Check party logistics'),
   'The Paid Shortcut', 'A route broker charges new climbers for a passage that may no longer be safe.',
   ('Verify the passage report','Interview the returning climbers'),
   ('Publish the corrected route warning','Escort the stranded novices'),
   ('Build a shared rest camp','Maintain an independent route registry')),
 'Reincarnated as a Slime': ('Rell Vale','settlement builder',('Maintain water channels','Prepare communal meals','Repair trade carts','Survey settlement paths'),
   'The Shared Crossing', 'Two communities dispute access to the same reliable river crossing.',
   ('Survey the seasonal river levels','Listen to both communities’ needs'),
   ('Broker a shared crossing schedule','Help establish an alternative ferry'),
   ('Fund a common shelter','Create a joint maintenance council')),
 'Custom World': ('Ari Vale','scout',('Deliver local parcels','Repair public paths','Sort market supplies','Help the local clinic'),
   'The Broken Agreement', 'A trade agreement has left smaller households without reliable supplies.',
   ('Read the agreement with its witnesses','Help households share what remains'),
   ('Seek public arbitration','Negotiate direct deliveries'),
   ('Create a relief shelter','Establish a public supply register')),
}
AMBITIONS={'explorer':'Explore five mapped locations', 'community':'Finish a local story and build a lasting community benefit',
           'leader':'Recruit a companion through an explicit membership decision', 'craft':'Complete ten paid shifts and teach an apprentice'}

def flavor(s): return FLAVOR.get(s.get('world'),FLAVOR['Custom World'])
def minute(s): return int(s.get('canon_time_minutes',0))
def token(name): return hashlib.sha256(name.encode()).hexdigest()[:16]
def read(s):
    result=copy.deepcopy(s.get('offline_life') or {})
    old=((s.get('offline_choices') or {}).get('rpg') or {})
    for k,v in {'career':old.get('career',0),'bonds':old.get('bonds',{}),'visits':{},'stories':{},'log':[],
                'legacy':old.get('legacy',[]),'recruits':{},'lessons':0,'retired':False}.items(): result.setdefault(k,v)
    return result
def wage(s): return max(.01,round(float(expansion_for(s.get('world')).get('currency_baseline',250))*.08,2))
def paid(s): return expansion_for(s.get('world')).get('tracks_currency',True)
def people(s,place):
    from living_adventures import available_people
    return available_people(s,place)
def row(key,label,category,minutes,description,**kw):
    return dict(id='offline:'+key,label=label,category=category,minutes=minutes,description=description,**kw)

def actions(s,place):
    r=read(s); f=flavor(s); out=[]; w=wage(s); money=currency_balance(copy.deepcopy(s))
    for ambition,label in AMBITIONS.items():
        if not r.get('ambition'): out.append(row('ambition:'+ambition,'Ambition: '+label,'Life',0,'Choose a personal direction. This does not grant power or change your rank.'))
    for i,label in enumerate(f[2]):
        pay=round(w*(1+min(2,r['career']//5)*.25),2) if paid(s) else 0
        out.append(row('work:'+str(i),label,'Work',480,f"A normal shift. {'Earn '+str(pay)+' '+str((s.get('currency') or {}).get('name','currency')) if pay else 'Earn local service credit'}. Five shifts improve your career tier; no official rank is awarded.",pay=pay))
    for length in (1440,10080,43200):
        out.append(row('downtime:'+str(length),'Quiet life: '+{1440:'one day',10080:'one week',43200:'one month'}[length],'Life',length,
            'Spend time on ordinary daily life. The real calendar, property income and world plans advance; declared local events interrupt. No automatic training or relationship rewards.'))
    pool=people(s,place)
    recruit_name=f[0]+' of '+place
    stage=r['recruits'].get(recruit_name,'unmet')
    if stage=='unmet': out.append(row('meet:'+token(recruit_name),'Meet a local '+f[1],'People',60,
        f'{recruit_name} is seeking practical field experience. Meeting them does not make them a member.',person=recruit_name))
    elif stage=='met' and any(p['name']==recruit_name for p in pool):
        out.append(row('trial:'+token(recruit_name),'Work alongside '+recruit_name,'People',240,'Complete a shared field exercise. They will then consider an independent expedition together.',person=recruit_name))
    elif stage=='ready' and any(p['name']==recruit_name for p in pool):
        out.append(row('recruit:'+token(recruit_name),'Form an independent company with '+recruit_name,'People',60,
            'Confirm membership for you and this willing companion in your independent company. This becomes the selected party; existing organization memberships remain recorded.',person=recruit_name))
    for person in pool:
        name=person['name']; t=token(name)
        if name not in r['visits'] or minute(s)-r['visits'][name]>=7*1440:
            for topic,label in [('memory','Share a personal memory'),('help','Help with an everyday concern'),('plans','Discuss your next journey')]:
                out.append(row('bond:'+t+':'+topic,label+' — '+name,'People',120,'Deepen this connection once per seven days. Different topics record different shared experiences.',person=name,topic=topic))
        if r['bonds'].get(name,0)>=3 and name not in r.get('promises',[]):
            out.append(row('promise:'+t,'Make a mutual promise — '+name,'Life',60,'Commit to helping each other return safely. Records a lasting relationship milestone, not automatic obedience.',person=name))
    story=r['stories'].get(place,{'stage':0,'choices':[]}); stage=story['stage']
    if stage<3 and not r['retired']:
        for choice,label in enumerate(f[5+stage]):
            grant=story.get('choices',[1])[0]==0 if story.get('choices') else False
            cost=round(w*(1 if grant else 2),2) if stage==2 and choice==0 and paid(s) else 0
            if money<cost: continue
            effect=('The final choice creates a local shelter (+25% ordinary recovery).' if stage==2 and choice==0 else
                    'The final choice restores the shortest local supply link (15% shorter mapped travel).' if stage==2 else
                    ('Documented evidence unlocks a grant covering half the eventual refuge cost.' if stage==0 and choice==0 else
                     'Direct aid earns supplies that restore 10% of your ordinary health and energy.' if stage==0 else
                     'Public accountability establishes three days of field preparation.' if choice==0 else
                     'Private mediation earns one ordinary shift of pay (or service credit where money is untracked).'))
            out.append(row(f'story:{stage}:{choice}',f[3]+': '+label,'Local story',120 if stage<2 else 480,
                f[4]+' '+effect,cost=cost,currency=(s.get('currency') or {}).get('name'),stage=stage,choice=choice))
    if r['career']>=5 and not r.get('apprentice'):
        out.append(row('mentor','Take on a practical apprentice','Life',120,'After five completed shifts, offer supervised practical training. Four weekly lessons establish their independence.'))
    if r.get('apprentice') and r['lessons']<4 and ('lesson_at' not in r or minute(s)-r['lesson_at']>=10080):
        out.append(row('lesson','Teach your apprentice','Life',240,'One practical lesson per week. The fourth records a teaching legacy.'))
    if r['legacy']:
        out.append(row('return' if r['retired'] else 'retire','Return to adventuring' if r['retired'] else 'Retire from adventure work','Life',60,
            'Change your personal life chapter. Retirement keeps ordinary life, work and relationships available; returning is reversible.'))
    return out

def validate(s,spec):
    from relationship_life import available
    name=spec.get('person')
    if name and not spec['id'].startswith('offline:meet:'):
        if not available(s,name) or name not in {p['name'] for p in people(s,spec['place'])}:
            raise ValueError('This person is no longer available here. Cancel the unfinished activity.')

def resolve(game,spec):
    s=game.state; r=read(s); s['offline_life']=r; f=flavor(s); action=spec['id'].split(':')[1:]; key=action[0]; place=spec['place']
    validate(s,spec)
    message=''
    if key=='ambition': r['ambition']=action[1]; message='Your ambition: '+AMBITIONS[action[1]]+'.'
    elif key=='work':
        r['career']+=1
        if spec['pay']: record_currency_transaction(s,spec['pay'],spec['label'],'work_income',source='offline_life')
        r['service']=r.get('service',0)+1
        message=f"You complete {spec['label'].lower()} in {place}. Career experience {r['career']}; tier {1+min(2,r['career']//5)}. "+(f"Earned {spec['pay']:g} {(s.get('currency') or {}).get('name','currency')}." if spec['pay'] else 'Your service is recorded without inventing a salary.')
    elif key=='downtime': message='Daily life continues in '+place+'. You keep ordinary commitments while the world calendar and established plans advance.'
    elif key=='meet':
        name=spec['person'];r['recruits'][name]='met'
        for field in ('contacts','npc_memories'):
            s.setdefault(field,{})[name]={'name':name,'kind':'person','role':f[1],'status':'Known','alive':True,'last_known_location':place,'public_goal':'Find reliable partners for field work.'}
        message=f"You meet {name}, a {f[1]}. They propose working together before making any commitment. They are a contact, not a member."
    elif key=='trial': r['recruits'][spec['person']]='ready';message=spec['person']+' completes a practical field exercise with you and offers to join an independent company. The membership decision is yours.'
    elif key=='recruit':
        from organizations import _queue_offer,resolve_membership_offer
        name=spec['person'];group=s.get('name','Traveler')+' — independent company'
        for person in (s.get('name','Traveler'),name):
            offer=_queue_offer(s,'recruit',group,person,'Player-confirmed independent expedition after a completed local trial.',leader=s.get('name'))
            if offer:resolve_membership_offer(s,offer['id'],'accept')
        r['recruits'][name]='joined'; r['legacy'].append('Founded a company with '+name)
        message=name+' joins your independent company. The current membership ledger now supplies the Team screen and command permissions.'
    elif key=='bond':
        name=spec['person'];r['visits'][name]=minute(s);r['bonds'][name]=r['bonds'].get(name,0)+1
        beats={'memory':'You exchange memories of the people who shaped you.','help':'You share an ordinary task and discuss what help each of you can realistically offer.','plans':'You compare hopes for the next journey and agree which risks you will not take.'}
        message=name+': '+beats[spec['topic']]+f" Bond {r['bonds'][name]}."
        relation=s.setdefault('relationships',{}).setdefault(name,{'score':0})
        if isinstance(relation,dict):relation['score']=min(100,int(relation.get('score',0))+3)
    elif key=='promise':
        r.setdefault('promises',[]).append(spec['person']);r['legacy'].append('Mutual promise with '+spec['person']);message=r['legacy'][-1]+'. You agree to support each other without giving up the freedom to refuse a dangerous request.'
    elif key=='story':
        story=r['stories'].setdefault(place,{'stage':0,'choices':[]})
        if story['stage']!=spec['stage']:raise ValueError('This story stage has already changed.')
        if spec.get('cost'):record_currency_transaction(s,-spec['cost'],spec['label'],'community_project',source='offline_life')
        earlier=' Your earlier approach '+('focused on evidence.' if story['choices'] and story['choices'][0]==0 else 'put immediate help first.') if story['choices'] else ''
        story['choices'].append(spec['choice']);story['stage']+=1
        message=f"{f[3]} — {f[5+spec['stage']][spec['choice']]}.{earlier} "
        if story['stage']<3:
            if spec['stage']==0 and spec['choice']==1:
                for field in ('hp','resource'):
                    cap=max(1,int(s.get(field+'_max',100)));s[field]=min(cap,float(s.get(field,0))+round(cap*.1))
                message+='The crews share restorative supplies: ordinary health and energy recover by 10%. '
            if spec['stage']==1 and spec['choice']==0:
                s.setdefault('adventures',{})['preparation']={'origin':place,'expires':minute(s)+4320,'prepared_minute':minute(s)}
                message+='Public route reports provide three days of field preparation. '
            elif spec['stage']==1 and spec['choice']==1:
                if paid(s):record_currency_transaction(s,wage(s),'Local mediation stipend','work_income',source='offline_life')
                else:r['service']=r.get('service',0)+1
                message+='The mediation earns a normal shift stipend or local service credit. '
            message+=('The people affected agree to present a documented case. ' if spec['choice']==0 else 'A practical support network forms while the official dispute continues. ')
            message+='The next decision is now available in Local story.'
        else:
            if spec['choice']==0:
                local=s.setdefault('location_details',{}).setdefault(place,{});local['adventure_shelter']=True
                local.setdefault('services',[])
                if 'Community refuge' not in local['services']:local['services'].append('Community refuge')
                message+='A community refuge opens. Ordinary recovery here improves by 25%.'
            else:
                from simulation_integrity import build_travel_graph
                edges=build_travel_graph(s)['edges'].get(place,[])
                if edges:
                    dest=min(edges,key=lambda e:e['minutes'])['to'];s.setdefault('world_benefits',{})['offline:'+token(place)]={'active':True,'kind':'safer_route','origin':place,'destination':dest,'factor':.85,'source':f[3]}
                    message+='A reliable supply link to '+dest+' is established: mapped travel takes 15% less time.'
                else:
                    s.setdefault('location_details',{}).setdefault(place,{})['adventure_shelter']=True
                    message+='With no mapped exit, the community establishes a refuge instead: recovery improves by 25%.'
            r['legacy'].append(f[3]+' at '+place)
            s.setdefault('location_details',{}).setdefault(place,{})['offline_story_outcome']=message
    elif key=='mentor':r['apprentice']=True;message='A local apprentice begins supervised practical instruction. They will need four weekly lessons, not an instant promotion.'
    elif key=='lesson':
        r['lessons']+=1;r['lesson_at']=minute(s);message=f"Practical lesson {r['lessons']}/4 completed."
        if r['lessons']==4:r['legacy'].append('Taught an independent apprentice');message+=' Your apprentice can now work independently.'
    elif key in ('retire','return'):r['retired']=key=='retire';message='You begin a quieter chapter of life.' if r['retired'] else 'You return to adventure work.'
    if r['legacy']:
        from life_simulation import record_legacy
        for item in r['legacy']:record_legacy(s,item,item,kind='offline_life')
    r['log'].append({'text':message,'minute':minute(s)});r['log']=r['log'][-80:]
    return message

def view(s):
    r=read(s)
    visited={s.get('location')}
    for trip in s.get('travel_history',[]):
        if trip.get('completed'):visited.update([trip.get('origin'),trip.get('destination')])
    visited.discard(None)
    achieved={'explorer':len(visited)>=5,
              'community':any(x.get('stage',0)>=3 for x in r['stories'].values()),
              'leader':'joined' in r['recruits'].values(), 'craft':r['career']>=10 and r['lessons']>=4}
    return {'ambition':AMBITIONS.get(r.get('ambition'),'Choose your own direction'), 'career':r['career'],
            'ambition_complete':achieved.get(r.get('ambition'),False),
            'bonds':r['bonds'],'legacy':r['legacy'],'retired':r['retired'],'recent':r['log'][-3:],
            'stories_completed':sum(x.get('stage',0)>=3 for x in r['stories'].values())}

def migrate(s):
    """Recover only Preview 5's synthetic local nodes; preserve the original save."""
    old=((s.get('offline_choices') or {}).get('rpg') or {})
    home=old.get('home'); current=s.get('location','')
    if home and current.startswith(home+' — ') and old.get('node') in (1,2):
        from simulation_integrity import _map_nodes
        mapped={n['name'] for n in _map_nodes(s.get('world','Custom World'))}
        if current not in mapped and home in mapped:
            s['location']=home
            s.setdefault('_pending_chronicle_notes',[]).append('Offline update: returned from the previous prototype’s local encounter area to '+home+'. Travel now uses the current world atlas. Your previous choices remain in the save history.')
    old_combat=s.get('combat') or {}
    if old_combat.get('offline_rpg'):
        s['combat']['active']=False
        s.setdefault('_pending_chronicle_notes',[]).append('The previous prototype battle has ended without rewards. New encounters use the current tactical engine.')
