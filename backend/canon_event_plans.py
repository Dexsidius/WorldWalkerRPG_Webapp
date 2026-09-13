"""Authored appointment casts and bounded local branches, never AI-generated.

Titles join the existing calendar; no replacement IDs or invented canon dates.
Each row: title | required cast | local situation | contribution | receipt.
Contributions help with the stated task, NOT the entire canonical outcome.
Historical-only entries remain reference history under the existing calendar.
"""
from functools import lru_cache

ROWS = {
'Naruto': '''
Konohagakure is founded|Hashirama Senju;Madara Uchiha|The clans are discussing a shared village.|Help survey the proposed settlement|You mark a usable meeting ground for the clans. Their political agreement remains theirs to decide.
Hashirama defeats Madara Uchiha|Hashirama Senju;Madara Uchiha|A confrontation threatens the valley approaches.|Guide travelers off the valley road|You clear travelers from the approach. You have not decided the duel.
The First Shinobi World War ends|Tobirama Senju;Hiruzen Sarutobi|Surviving shinobi need a route home.|Organize a reception for returning teams|You record the returning teams and direct the wounded to care.
The Second Shinobi World War begins|Hanzo|War is disrupting the roads around Rain.|Mark a civilian evacuation route|You mark a route away from the military roads. This does not end the war.
Sakumo Hatake's death|Sakumo Hatake|Sakumo has withdrawn after the public condemnation of his mission.|Leave a personal offer of support|You offer Sakumo company without demanding an answer. An offer alone does not resolve his crisis.
The original Akatsuki is founded|Yahiko;Nagato;Konan|Yahiko is gathering people willing to help Rain's communities.|Help organize a civilian meeting|You prepare a meeting place and record the needs raised by local residents.
The Kannabi Bridge mission|Kakashi Hatake;Obito Uchiha;Rin Nohara|A Leaf team is operating near an enemy supply route.|Mark an extraction point|You mark an extraction point away from the bridge. The mission itself remains dangerous.
Yahiko's death and Akatsuki's transformation|Yahiko;Nagato;Konan;Hanzo|An armed meeting has become a hostage confrontation.|Study the hostage escape route|You identify cover between the meeting ground and the nearest withdrawal route.
Naruto's birth and the Nine-Tails attack|Minato Namikaze;Kushina Uzumaki;Obito Uchiha|The village is under attack and shelters are filling.|Direct civilians to shelter|You help civilians reach shelter without entering the sealing confrontation.
Might Duy's sacrifice|Might Duy;Might Guy;Ebisu;Genma Shiranui|Duy's team is trapped by Mist swordsmen.|Mark a withdrawal route|The retreat has a marked route.
The Hyūga Affair|Hiashi Hyuga;Hizashi Hyuga|An incident involving the Hyuga compound is becoming a diplomatic dispute.|Record witness testimony for the inquiry|You preserve testimony for the inquiry. Responsibility is not decided by rumor.
The Uchiha Massacre|Itachi Uchiha;Obito Uchiha;Sasuke Uchiha|The Uchiha district is suddenly unsafe.|Find an exit from the district|You locate an exit and a place where survivors could seek help.
Academy graduation night — the Mizuki incident|Naruto Uzumaki;Iruka Umino;Mizuki|An Academy student is missing and Iruka is searching.|Help Iruka search the nearby paths|You check the paths and report what you actually saw to Iruka.
Ninja Registration Day|Naruto Uzumaki;Konohamaru Sarutobi|New genin are completing their registration.|Help sort the registration queue|You help applicants find the right desk. Nobody receives a rank from this assistance.
The Graduation Ceremony|Iruka Umino|Graduates and their families are gathering at the Academy.|Help prepare the ceremony|You prepare seating and welcome the families arriving at the Academy.
Team 7 is formed|Kakashi Hatake;Naruto Uzumaki;Sasuke Uchiha;Sakura Haruno|Kakashi is arranging his new team's first evaluation.|Help prepare the training ground|You clear the training ground. Team 7 must still pass Kakashi's evaluation.
D-rank missions begin|Naruto Uzumaki;Sasuke Uchiha;Sakura Haruno|The mission desk is assigning ordinary village work.|Help organize the mission desk|You sort local requests so available teams can find their assignments.
The client's request|Tazuna;Kakashi Hatake|Tazuna is arranging an escort to the Land of Waves.|Help check the escort provisions|You check the provisions. You have not learned information Tazuna has withheld.
Land of Waves mission begins|Tazuna;Kakashi Hatake;Zabuza Momochi|An escort party is approaching a threatened bridge project.|Help prepare shelter for the builders|You prepare shelter for the bridge workers, separate from the escort's fight.
Zabuza's ambush|Zabuza Momochi;Kakashi Hatake;Haku|Mist obscures the road around the escort party.|Mark cover away from the road|You mark nearby cover without identifying anyone concealed in the mist.
A quiet conversation in the woods|Naruto Uzumaki;Haku|Two young travelers are talking beside the forest path.|Offer tea to the travelers|You share a quiet pause. Their names and motives are not revealed merely by overhearing them.
Battle of the Great Naruto Bridge|Zabuza Momochi;Haku;Kakashi Hatake;Gato|Fighting threatens the bridge and the workers nearby.|Guide workers off the bridge|You guide workers away from the fighting. The combatants' fates remain unresolved.
Team 7 returns from the Land of Waves|Kakashi Hatake;Naruto Uzumaki;Sasuke Uchiha;Sakura Haruno|A tired escort team is returning to the village.|Help receive the returning team|You arrange a quiet place for the team to recover and file its report.
Chūnin Exam nominations|Kakashi Hatake;Kurenai Yuhi;Asuma Sarutobi|Squad leaders are considering exam nominations.|Help prepare the candidate briefing|You organize the briefing materials. Only the responsible leaders can nominate candidates.
Chūnin Exams begin|Orochimaru;Anko Mitarashi|Candidates are entering the exam grounds.|Help staff the public first-aid point|You prepare the first-aid point outside the restricted exam area.
Chūnin Exam preliminaries|Hayate Gekko|Examiners are arranging the preliminary bouts.|Help organize the waiting area|You keep the waiting area clear for candidates and medical staff.
One month of final-round training|Jiraiya;Naruto Uzumaki;Kakashi Hatake;Sasuke Uchiha|Finalists are using the training grounds.|Assist with training-ground setup|You set up practice targets. No technique or mastery is awarded by this chore.
The curse mark's temptation|Sasuke Uchiha;Kakashi Hatake|Sasuke's condition is being handled privately by his mentor.|Deliver supplies to the training-ground entrance|You leave the supplies at the entrance without gaining access to private medical information.
Chūnin Exam finals and the Konoha Crush|Orochimaru;Hiruzen Sarutobi|The finals draw a crowd while security watches the village.|Help organize the spectators' exits|You identify exits for spectators. Preparing an exit does not prevent an invasion.
The search for Tsunade begins|Jiraiya;Naruto Uzumaki;Tsunade|A traveling pair is preparing to seek a healer.|Help stock the travelers' supplies|You stock ordinary travel supplies without deciding Tsunade's answer.
Tsunade becomes Fifth Hokage|Tsunade|The village is preparing for a new Hokage's administration.|Help receive the hospital requests|You sort requests for the hospital. Tsunade's appointment does not grant you office.
Sasuke's Departure|Sasuke Uchiha|There are signs of an unauthorized departure.|Report the signs to the village watch|You report the trail you found; the watch can use it without learning anything you did not observe.
Sasuke Retrieval Mission|Sasuke Uchiha;Shikamaru Nara;Naruto Uzumaki|A retrieval team is following a dangerous trail.|Mark a fallback point for the team|You mark a fallback point and leave basic supplies for the returning team.
Naruto departs with Jiraiya|Naruto Uzumaki;Jiraiya|Naruto and Jiraiya are preparing for a long journey.|Help prepare their departure|You help pack the departure supplies and wish them well.
Naruto returns after the training journey|Naruto Uzumaki;Jiraiya|Naruto is returning after a long absence.|Welcome the returning travelers|You welcome the travelers without assuming knowledge of their private training.
Gaara's death and rescue|Gaara;Deidara;Sasori;Chiyo|Sand's leadership is in danger and rescue preparations are underway.|Help organize a rescue supply point|You establish a supply point. Retrieving Gaara remains a separate task.
Asuma Sarutobi's death|Asuma Sarutobi;Hidan;Shikamaru Nara|Asuma's team faces a dangerous Akatsuki encounter.|Prepare a casualty withdrawal point|You prepare cover and supplies for a withdrawal from the confrontation.
Jiraiya's death in Amegakure|Jiraiya;Nagato;Konan|A lone shinobi is investigating the rain-soaked city.|Check a nearby escape passage|You check a passage from the investigation area without learning the enemy's hidden abilities.
Itachi Uchiha's death|Itachi Uchiha;Sasuke Uchiha|The Uchiha brothers are approaching a private confrontation.|Clear bystanders from the approach|You guide bystanders away. You have not settled either brother's intentions.
Itachi's Truth|Sasuke Uchiha;Obito Uchiha|A private conversation is taking place away from the main road.|Leave water at the outer shelter|You leave water outside. Private revelations are not added to your knowledge.
Pain's Assault on Konoha|Nagato;Konan|Konoha's defenses are preparing for a major threat.|Help open civilian shelters|You prepare shelters and organize their entrances.
Naruto vs. Pain|Naruto Uzumaki;Nagato|A confrontation is unfolding amid Konoha's damaged streets.|Help move survivors away from the battlefield|You move survivors clear. The confrontation and any later negotiation remain separate.
The Five Kage Summit|Gaara;Danzo Shimura;Mei Terumi;Onoki;Ay|Delegations are gathering under Iron Country's protection.|Help prepare the delegates' public reception|You help with the public reception without entering closed negotiations.
Obito's Reveal|Obito Uchiha;Kakashi Hatake;Might Guy;Naruto Uzumaki|A masked opponent is engaged on the war front.|Help clear a fallback lane|You mark a lane for wounded allies without assuming the masked opponent's identity is known.
The Fourth Shinobi World War begins|Obito Uchiha;Kabuto Yakushi|Allied forces are mobilizing across the front.|Help establish a field aid station|You establish a field aid point. Command of the alliance remains separate.
Kaguya's Appearance|Madara Uchiha;Black Zetsu;Kaguya Otsutsuki|The battlefield is being transformed by an unfamiliar power.|Find shelter from the changing terrain|You identify nearby cover. This does not explain the source of the phenomenon.
Naruto and Sasuke vs. Kaguya|Naruto Uzumaki;Sasuke Uchiha;Kaguya Otsutsuki|A dimensional battlefield is separating the combatants.|Mark a nearby regrouping point|You mark a point within the space you can reach, not a new dimensional exit.
Naruto vs. Sasuke — Final Valley|Naruto Uzumaki;Sasuke Uchiha|Two exhausted shinobi are approaching the valley.|Keep travelers away from the valley|You guide travelers away from the confrontation.
Kakashi becomes Sixth Hokage|Kakashi Hatake|Konoha is preparing a change of administration.|Help organize the reconstruction requests|You sort reconstruction requests for the incoming administration.
Naruto and Hinata marry|Naruto Uzumaki;Hinata Hyuga|Friends and relatives are preparing a wedding celebration.|Help prepare the celebration|You help prepare the celebration without claiming an invitation to private family conversations.
Naruto Becomes Hokage|Naruto Uzumaki;Kakashi Hatake|The village is preparing a Hokage inauguration.|Help prepare the public gathering|You help organize the public gathering. Political authority is not transferred to you.
Momoshiki and Kinshiki's attack|Momoshiki Otsutsuki;Kinshiki Otsutsuki;Naruto Uzumaki|An extraordinary threat is approaching the exam venue.|Prepare the arena evacuation paths|You prepare paths for spectators to leave the arena.
''',
'One Piece': '''
Gol D. Roger's execution|Gol D. Roger|Crowds are gathering at the execution square.|Help keep an exit clear|You keep a path open through the crowd. You have not changed the execution order.
Portgas D. Ace is born|Portgas D. Rouge|A household needs privacy and supplies.|Leave supplies with a trusted local helper|You leave household supplies without learning a child's concealed identity.
The Ohara Incident|Nico Robin;Jaguar D. Saul|The island's residents face a military emergency.|Prepare an evacuation gathering point|You mark a place for civilians to gather away from the approaching danger.
The execution of Kozuki Oden|Kozuki Oden;Kaido;Kurozumi Orochi|People are gathering under guard for a public punishment.|Find shelter for frightened bystanders|You help bystanders reach shelter without defeating the occupying forces.
Monkey D. Luffy is born|Monkey D. Garp|News of a birth is being shared within a family.|Deliver a small care package|You leave a care package without being granted access to family secrets.
Fisher Tiger's death|Fisher Tiger|An injured captain's crew is trying to secure help.|Help prepare a medical landing point|You prepare a landing point. Treatment decisions remain with the patient and crew.
Ace joins the Whitebeard Pirates|Portgas D. Ace;Edward Newgate|A pirate crew is considering a new member.|Help with the crew's shared meal|You help prepare a meal; membership and allegiance remain personal decisions.
Marshall D. Teach betrays the Whitebeard Pirates|Marshall D. Teach;Thatch|Tension aboard a pirate ship is escalating.|Offer to watch the common passage|You watch the common passage without learning concealed intentions.
Luffy leaves Foosha Village|Monkey D. Luffy|A young sailor is preparing to leave the harbor.|Help check the small boat's supplies|You check the supplies. The sailor still chooses where to go.
Shells Town upheaval|Monkey D. Luffy;Roronoa Zoro;Morgan|A Marine base is at the center of a local dispute.|Prepare a safe gathering point outside the base|You prepare a gathering point without overruling the base commander.
Orange Town crisis|Buggy;Nami;Monkey D. Luffy|Pirate violence is threatening the town.|Help residents find shelter|You guide residents toward shelter away from the main street.
Syrup Village conspiracy|Kuro;Kaya;Usopp|Unusual activity is disturbing the village approaches.|Record the activity at the shore|You record what you observed without identifying a conspiracy by guesswork.
Kaya's decision and the Going Merry|Kaya;Usopp|A ship and its supplies are being prepared at the shore.|Help load the departure supplies|You help load supplies. Ownership of the ship remains Kaya's decision.
Baratie conflict|Sanji;Don Krieg;Dracule Mihawk|Armed visitors threaten the floating restaurant.|Help move diners away from the fighting|You guide diners away from the exposed deck.
Arlong Park revolt|Nami;Genzo;Nojiko|Villagers are confronting an occupation.|Mark a civilian withdrawal route|The civilians have a marked withdrawal route.
Loguetown and the first bounty|Monkey D. Luffy;Smoker;Buggy|Crowds and Marines are converging near the execution square.|Help clear a route out of the square|You clear a route through the crowd. Bounties are not awarded for helping bystanders.
Reverse Mountain and Laboon's promise|Laboon;Crocus;Monkey D. Luffy|A ship has reached the waters near a waiting whale.|Help check the mooring lines|You help secure the vessel. A promise to Laboon must still be made by the person giving it.
Little Garden and Vivi's true identity|Dorry;Brogy;Nefertari Vivi|Travelers are trying to establish a camp on a dangerous island.|Help prepare a safe camp perimeter|You prepare a perimeter without discovering a traveler's concealed identity.
Drum Island — Chopper joins|Tony Tony Chopper;Kureha;Wapol|A winter settlement is caught in a struggle over its castle.|Help stock the village medical point|You stock basic supplies. Medical treatment and Chopper's choice remain separate.
Operation Utopia and Crocodile's defeat|Crocodile;Nefertari Vivi;Monkey D. Luffy|Civil unrest is threatening Alabasta's population.|Help establish a civilian water point|You establish a water point. This alone neither defeats Crocodile nor ends the rebellion.
Skypiea's golden bell rings|Enel;Monkey D. Luffy|A conflict threatens the sky island's communities.|Help prepare a sheltered gathering place|You prepare shelter while the conflict remains unresolved.
Water 7 — the search for Robin|Nico Robin;Monkey D. Luffy;Iceburg|People are searching the city amid growing accusations.|Collect statements from willing witnesses|You preserve witness statements without declaring accusations proven.
Enies Lobby raid — war on the World Government|Nico Robin;Rob Lucci;Monkey D. Luffy|A rescue party is approaching a government stronghold.|Mark a fallback point near the approach|You mark a fallback point. Entering the stronghold remains dangerous.
Thriller Bark — Moria defeated|Gecko Moria;Brook;Monkey D. Luffy|Travelers are trapped in a hostile ship settlement.|Help prepare a refuge for survivors|You prepare a refuge without restoring stolen shadows by assumption.
Sabaody Archipelago incident|Kizaru;Silvers Rayleigh;Monkey D. Luffy|An escalating confrontation is drawing Marine forces.|Guide bystanders away from the grove|You guide bystanders away before the approaches become crowded.
Impel Down infiltration|Monkey D. Luffy;Magellan|A prison emergency is disrupting the passages.|Mark a fallback point in the accessible corridor|You mark a fallback point only in the corridor you can reach.
The Battle of Marineford|Edward Newgate;Sengoku;Portgas D. Ace|Fleets are confronting the execution force.|Prepare a casualty collection point|You prepare a collection point away from the direct clash.
Ace's death|Portgas D. Ace;Sakazuki;Monkey D. Luffy|Ace and Luffy face an immediate threat on the battlefield.|Identify a withdrawal lane|You identify a withdrawal lane. Ace has not been rescued yet.
Luffy begins two years of training|Monkey D. Luffy;Silvers Rayleigh|A survivor is preparing for secluded training.|Leave provisions at the departure point|You leave provisions without learning private training methods.
Reunion at Sabaody|Monkey D. Luffy;Roronoa Zoro;Nami|A scattered crew is gathering to depart.|Help prepare the harbor supplies|You prepare supplies. Crew membership remains distinct from helping at the harbor.
Fishman Island saved|Hody Jones;Shirahoshi;Monkey D. Luffy|Violence threatens Fishman Island's residents.|Help organize a civilian refuge|You prepare a refuge without settling the island's government.
Punk Hazard incident|Caesar Clown;Trafalgar Law;Monkey D. Luffy|A dangerous facility is losing control of its surroundings.|Help prepare a clean-air collection point|You prepare a collection point away from visible gas. This does not neutralize the facility.
Dressrosa liberated|Donquixote Doflamingo;Monkey D. Luffy;Trafalgar Law|The city is becoming a battlefield.|Mark a shelter for displaced residents|You mark a shelter while the battle over the city remains unresolved.
The Alliance forms at Zou|Kozuki Momonosuke;Inuarashi;Nekomamushi|Delegates are discussing a possible alliance.|Help arrange the delegates' reception|You arrange the reception. You cannot sign an alliance on their behalf.
Whole Cake Island — the Tea Party interrupted|Charlotte Linlin;Sanji;Monkey D. Luffy|A guarded celebration is drawing important guests.|Help prepare an outer reception point|You help at the outer reception without learning the guests' secret plans.
Landing in Wano|Monkey D. Luffy;Tama|New arrivals are seeking shelter in a troubled country.|Help establish a small travelers' shelter|You prepare shelter without granting the arrivals control of the country.
Nefertari Cobra's death and Imu's reveal|Nefertari Cobra;Imu;Sabo|A royal delegation is moving through guarded government halls.|Prepare a rendezvous outside the closed chamber|You prepare a rendezvous without learning what is said inside the chamber.
The Raid on Onigashima — Wano liberated|Kaido;Kozuki Momonosuke;Monkey D. Luffy|An alliance is preparing to challenge the occupying forces.|Help prepare a casualty landing point|You prepare a landing point. Defeating the occupiers and establishing government remain separate.
Lulusia Kingdom is destroyed|Imu|Reports of an extraordinary threat are disturbing the kingdom.|Help identify civilian shelter routes|You identify shelter routes; ordinary shelters are not proof against the threat.
Egghead Island incident|Vegapunk;Kizaru;Monkey D. Luffy|A research island is facing a military blockade.|Help establish an evacuation assembly point|You establish an assembly point without breaking the blockade.
''',
'Bleach': '''
Turn Back the Pendulum|Shinji Hirako;Sosuke Aizen;Kisuke Urahara|An investigation is drawing officers away from their normal duties.|Prepare a return checkpoint|You prepare a checkpoint without discovering a concealed experiment.
Masaki Kurosaki's death|Masaki Kurosaki;Grand Fisher|A dangerous presence is near the river.|Guide pedestrians away from the riverbank|You guide pedestrians away without defeating the hidden threat.
Kaien Shiba's death|Kaien Shiba;Rukia Kuchiki|A spiritual-duty operation has become dangerous.|Prepare a casualty reception point|You prepare a reception point without identifying an unseen possession.
Rukia Kuchiki arrives in Karakura Town|Rukia Kuchiki;Ichigo Kurosaki|An unfamiliar disturbance is near the clinic.|Help clear the clinic entrance|You clear the entrance without gaining spiritual powers automatically.
Uryu Ishida makes himself known|Uryu Ishida;Ichigo Kurosaki|Spiritual disturbances are drawing attention across town.|Help guide residents to a safe street|You guide residents away from the visible disturbance.
Orihime and Chad's spiritual awareness grows|Orihime Inoue;Yasutora Sado|Two students are dealing with unfamiliar disturbances.|Offer a quiet place to recover|You offer a place to recover without defining anyone's powers for them.
Renji and Byakuya come for Rukia|Renji Abarai;Byakuya Kuchiki;Rukia Kuchiki|Two officers are confronting Rukia in town.|Guide bystanders away from the confrontation|You guide bystanders away. Rukia's detention remains unresolved.
Rukia is sentenced to execution|Rukia Kuchiki;Byakuya Kuchiki|An execution order is being circulated within Seireitei.|Submit a request for a lawful review|You submit a request. Filing it is not the same as overturning the sentence.
Training with Urahara Kisuke|Kisuke Urahara;Ichigo Kurosaki|Urahara is preparing a private training session.|Deliver supplies to the shop entrance|You deliver the supplies without gaining access to the private training area.
The push into Seireitei|Ichigo Kurosaki;Yoruichi Shihoin|An unauthorized party is approaching Seireitei.|Prepare a fallback point outside the gate|You prepare a fallback point without being granted entry to restricted areas.
Aizen's betrayal at Sokyoku Hill|Rukia Kuchiki;Renji Abarai|An execution ground is becoming a confrontation.|Mark a withdrawal route|The withdrawal route is marked.
Arrancar appear in Karakura|Yammy Llargo;Ulquiorra Cifer;Ichigo Kurosaki|Unfamiliar spiritual enemies are entering the town.|Help establish a civilian shelter|You establish shelter without knowing the visitors' abilities.
The Visored approach Ichigo|Shinji Hirako;Ichigo Kurosaki|A visitor is trying to speak privately with Ichigo.|Leave supplies outside the meeting place|You leave supplies without learning the group's concealed history.
Orihime is taken to Hueco Mundo|Orihime Inoue;Ulquiorra Cifer|Orihime faces pressure from an unfamiliar envoy.|Prepare a safe local rendezvous|You prepare a rendezvous. Crossing to another realm requires an actual route.
Hueco Mundo rescue begins|Ichigo Kurosaki;Uryu Ishida;Yasutora Sado|A rescue party is crossing hostile desert.|Help mark a desert regrouping point|You mark a regrouping point within the desert, not a portal to another realm.
Ichigo confronts Grimmjow|Ichigo Kurosaki;Grimmjow Jaegerjaquez|A confrontation is forming within Las Noches.|Clear the nearby corridor|You clear the corridor without deciding the duel.
Ichigo confronts Ulquiorra|Ichigo Kurosaki;Ulquiorra Cifer;Orihime Inoue|A dangerous confrontation is unfolding above Las Noches.|Prepare a sheltered fallback point|You prepare cover away from the confrontation.
The battle for Fake Karakura Town|Sosuke Aizen;Shunsui Kyoraku;Genryusai Yamamoto|Defenders are holding a prepared spiritual battlefield.|Help maintain a casualty collection point|You prepare a casualty point without granting victory over the attacking force.
Ichigo's final confrontation with Aizen|Ichigo Kurosaki;Sosuke Aizen;Kisuke Urahara|An immense spiritual confrontation is approaching its conclusion.|Clear the outer approach|You clear the approach without learning a concealed sealing plan.
Xcution enters Ichigo's life|Kugo Ginjo;Ichigo Kurosaki|A stranger is offering Ichigo a private arrangement.|Offer a neutral meeting place|You offer a meeting place without deciding whether Ichigo trusts the stranger.
Ichigo's Soul Reaper powers return|Ichigo Kurosaki;Rukia Kuchiki|Allies are preparing to help Ichigo confront a betrayal.|Help clear the meeting area|You clear the area. A special power restoration is not awarded by this assistance.
The Wandenreich declares war|Yhwach;Genryusai Yamamoto|A hostile declaration is reaching Soul Society.|Help circulate the public emergency instructions|You circulate the authorized instructions, not classified enemy intelligence.
The first invasion of Soul Society|Yhwach;Genryusai Yamamoto|Enemy forces are entering Seireitei.|Help open a medical fallback station|You open a fallback station while the fighting continues.
Royal Guard training|Ichigo Kurosaki;Ichibe Hyosube|The Royal Guard is preparing specialized training.|Deliver supplies to the authorized reception point|You deliver supplies without receiving Royal Guard training or access by assumption.
The second Wandenreich invasion|Yhwach;Shunsui Kyoraku|Seireitei faces another major assault.|Help maintain the evacuation corridors|You mark accessible evacuation corridors without creating a path through occupied walls.
The Soul King crisis|Yhwach;Ichigo Kurosaki;Soul King|A crisis in the palace threatens the balance between realms.|Find a nearby regrouping point|You identify a point within the palace space you can reach. The cosmic crisis remains unresolved.
Wahrwelt final battle|Yhwach;Ichigo Kurosaki;Uryu Ishida|The remaining combatants are approaching the final stronghold.|Prepare a fallback point within the stronghold|You prepare a local fallback point without opening a new realm route.
''',
}

# These are explicit causal links, not "previous chronological entry required".
# An altered predecessor blocks only these authored continuations, not a world's
# entire later calendar. Unwritten alternate continuations are honestly suspended.
REQUIRES = {
 'Naruto': {
  "Naruto's birth and the Nine-Tails attack": ['The Kannabi Bridge mission'],
  'The Uchiha Massacre': ['The Kannabi Bridge mission'],
  "Sasuke's Departure": ['The Uchiha Massacre'],
  'Sasuke Retrieval Mission': ["Sasuke's Departure"],
  "Jiraiya's death in Amegakure": ["Yahiko's death and Akatsuki's transformation"],
  "Pain's Assault on Konoha": ["Yahiko's death and Akatsuki's transformation"],
  'Naruto vs. Pain': ["Pain's Assault on Konoha"],
  "Obito's Reveal": ['The Kannabi Bridge mission'],
  'The Fourth Shinobi World War begins': ['The Kannabi Bridge mission'],
  "Itachi's Truth": ["Itachi Uchiha's death"],
  'Naruto and Sasuke vs. Kaguya': ["Kaguya's Appearance"],
 },
 'One Piece': {
  "Ace's death": ['The Battle of Marineford'],
  "Luffy begins two years of training": ["Ace's death"],
 },
 'Bleach': {
  'Rukia is sentenced to execution': ['Renji and Byakuya come for Rukia'],
  'Hueco Mundo rescue begins': ['Orihime is taken to Hueco Mundo'],
  'Royal Guard training': ['The first invasion of Soul Society'],
 },
}

# Rescue victories save this target, not an island, war, or every named person.
# Enemy power is an authored encounter benchmark; never scaled to the player.
RESCUES = {
 "Yahiko's death and Akatsuki's transformation": ('Yahiko', 'Rain ambush unit', 230, 5),
 'The Kannabi Bridge mission': ('Obito Uchiha', 'Iwa interception team', 180, 3),
 'Asuma Sarutobi\'s death': ('Asuma Sarutobi', 'Hidan', 420, 1),
 "Jiraiya's death in Amegakure": ('Jiraiya', 'Paths of Pain', 620, 6),
 "Ace's death": ('Portgas D. Ace', 'Sakazuki', 800, 1),
 'Renji and Byakuya come for Rukia': ('Rukia Kuchiki', 'Byakuya Kuchiki', 560, 1),
 'Orihime is taken to Hueco Mundo': ('Orihime Inoue', 'Ulquiorra Cifer', 600, 1),
}

# Preserve secrecy: the reference timeline is not a report available to NPCs.
PRIVATE = {
 'The Kannabi Bridge mission', "Yahiko's death and Akatsuki's transformation",
 'The curse mark\'s temptation', "Itachi's Truth", "Jiraiya's death in Amegakure",
 'Portgas D. Ace is born', 'Monkey D. Luffy is born',
 'Marshall D. Teach betrays the Whitebeard Pirates',
 "Nefertari Cobra's death and Imu's reveal", 'Turn Back the Pendulum',
 'Training with Urahara Kisuke', 'The Visored approach Ichigo',
 'Royal Guard training', 'The Soul King crisis',
}

# A prisoner can appear at a sentencing or rescue, not at an unrelated journey.
CAPTIVE_ROLES = {
 'Rukia is sentenced to execution': {'Rukia Kuchiki'},
 'The Battle of Marineford': {'Portgas D. Ace'},
 'Enies Lobby raid — war on the World Government': {'Nico Robin'},
}

@lru_cache(maxsize=3)
def catalog(world):
    result = {}
    for line in ROWS.get(world, '').strip().splitlines():
        if not line.strip():
            continue
        title, cast, brief, offer, receipt = line.split('|')
        if title in result:
            raise ValueError('Duplicate canon plan: '+title)
        result[title] = dict(title=title, actors=cast.split(';'), brief=brief,
                             offer=offer, contribution=receipt,
                             private=title in PRIVATE,
                             captive_roles=CAPTIVE_ROLES.get(title, set()),
                             requires=REQUIRES.get(world, {}).get(title, []),
                             rescue=RESCUES.get(title))
    return result
