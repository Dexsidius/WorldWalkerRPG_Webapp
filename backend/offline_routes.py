"""Offline-only, enumerated character creation and local life status."""
from flask import jsonify, request
from runtime_mode import offline_enabled
from worlds import WORLD_DATA, DIFFICULTIES, expansion_for, start_options_for, starting_eras_for, abilities_for

NAMES = ['Ari', 'Rowan', 'Kai', 'Mira', 'Ren', 'Sora', 'Tala', 'Nico', 'Ash', 'Robin', 'Yuna', 'Finch']
BACKGROUNDS = [
 ('A fresh start', 'I leave an ordinary home to build an independent life through practical experience.'),
 ('Community roots', 'I grew up helping neighbors and want to protect a place worth returning to.'),
 ('A working life', 'I learned a practical trade and seek honest work, reliable friends, and a chance to travel.'),
 ('An uncertain road', 'I have few possessions and no powerful patron. I want to earn my place through my choices.'),
]

def choices(world):
    ex=expansion_for(world)
    return {'origins':ex['origins'] or ['Local civilian'], 'archetypes':ex['archetypes'] or ['Practical novice','Martial trainee','Support specialist'],
            'starts':start_options_for(world) or [{'label':WORLD_DATA[world]['start'],'location':WORLD_DATA[world]['start']}],
            'eras':starting_eras_for(world) or [{'id':'default','label':'Main story opening'}]}

def creation(payload):
    if not isinstance(payload,dict):raise ValueError('Choose a character from the available selections.')
    world=payload.get('world')
    if world not in WORLD_DATA:raise ValueError('Choose an available world.')
    c=choices(world)
    def pick(key,values):
        value=payload.get(key)
        if value not in values:raise ValueError('Choose a listed '+key.replace('_',' ')+'.')
        return value
    name=pick('name',NAMES); origin=pick('origin',c['origins']); archetype=pick('archetype',c['archetypes'])
    location=pick('start_location',[x['location'] for x in c['starts']])
    era=pick('starting_era_id',[x['id'] for x in c['eras']])
    difficulty=pick('difficulty',DIFFICULTIES); age=pick('age',[18,21,25,30,40,50])
    background=pick('background',[x[0] for x in BACKGROUNDS])
    return dict(name=name,world=world,difficulty=difficulty,background=dict(BACKGROUNDS)[background],
        appearance_desc='Practical traveling clothes with a distinctive scarf.',custom_world='',origin=origin,
        archetype=archetype,stats={k:0 for k in abilities_for(world)},start_location=location,
        starting_era_id=era,age=age)

def register(app, get_game, acquire_busy, release_busy):
    @app.before_request
    def choice_only():
        if not offline_enabled():
            if request.path.startswith("/api/offline/"):return jsonify(error="Offline mode is not enabled."),404
            return None
        path=request.path
        blocked={'/api/campaign/new','/api/campaign/preview','/api/campaign/preview/reroll',
          '/api/action/submit','/api/event/respond','/api/actions/queue','/api/actions/update',
          '/api/chats/send','/api/advisor/ask','/api/time/assess','/api/time/resolve',
          '/api/quests/note','/api/quick_action','/api/portrait/identity','/api/portrait/generate',
          '/api/settings/test_ai','/api/settings/detect_models','/api/campaign/correct',
          '/api/campaign/correct/preview','/api/evaluations/run','/api/evaluations/compare'}
        if request.method=='POST' and (path in blocked or path.startswith(('/api/lore/','/api/multiplayer/','/api/auth/'))):
            return jsonify(error='This offline edition uses listed choices. Open Activities or select a mapped destination.'),400

    @app.get('/api/offline/creation')
    def metadata():
        return jsonify(names=NAMES,backgrounds=[x[0] for x in BACKGROUNDS],ages=[18,21,25,30,40,50],
            worlds={w:choices(w) for w in WORLD_DATA},difficulties=list(DIFFICULTIES))

    @app.post('/api/offline/create')
    def create():
        try: args=creation(request.get_json(force=True))
        except (ValueError,TypeError) as exc:return jsonify(error=str(exc)),400
        if not acquire_busy():return jsonify(error='An activity is still resolving.'),409
        try:
            game=get_game()
            game.new_campaign(**args)
            game.opening()
            return jsonify(state=game.public_state(),story=game._flush_story())
        except Exception as exc:return jsonify(error=str(exc)),400
        finally:release_busy()

    @app.get('/api/offline/life')
    def life():
        from offline_life import view
        game=get_game()
        with game.lock:return jsonify(view(game.state))
