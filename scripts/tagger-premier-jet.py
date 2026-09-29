import re, glob, os, yaml, sys
# à lancer depuis le dossier du cours (celui qui contient tags.yaml et slides/) ; usage unique, première passe
TAGS=set(yaml.safe_load(open('tags.yaml')).keys())
def texte(s):
    out=[]
    def rec(v):
        if isinstance(v,dict):
            if 'fr' in v and isinstance(v['fr'],str): out.append(v['fr']); return
            for k,x in v.items():
                if k=='en': continue
                rec(x)
        elif isinstance(v,list):
            for x in v: rec(x)
        elif isinstance(v,str): out.append(v)
    rec(s); return ' '.join(out).lower()
R=[
 ('kr-agent', r'tell\b|ask\b|agent réflexe|agent qui raisonne|niveau des connaissances|agents à base|thermostat|dedans et dehors|pourquoi un agent|système 1'),
 ('kr-grounding', r'coupure|carré syntaxe|bachimont|grounding|ancr'),
 ('kr-grounding', r'grounding|ancr'),
 ('kr-natural-language', r'langage naturel|langage courant|ambigu|implicature|sous-entend|vague|sorite|sapir|whorf|pinker|guugu|novlangue|orwell|pensées ne sont pas'),
 ('kr-formal-language', r'langage formel|leibniz|continuum|expressivit|ce que le langage formel|langage contrôlé'),
 ('kr-possible-worlds', r'mondes possibles|monde possible|mondes compatibles'),
 ('kr-semantics', r'conséquence logique|correct|complét|\\models|\\vdash|sémantique de la logique|tables de vérité|interprétation'),
 ('kr-rules', r'système expert|systèmes experts|base de règles|transport|dendral|mycin|prospector|x-con|acteurs|ingénieur de la connaissance'),
 ('kr-forward-chaining', r'chaînage avant|saturer|saturation|point fixe|propagation|graphe et-ou|graphe et/ou'),
 ('kr-backward-chaining', r'chaînage arrière|demandable|quelle question|entropie|vingt questions|valeur de l.information|dialogue|pourquoi \?|why'),
 ('kr-horn', r'horn|clauses?\b|linéaire'),
 ('kr-negation', r'négation|monde clos|non protégé|strate|stratif|spécificité|modèles stables|asp\b|answer set|échec|grover'),
 ('kr-confluence', r'confluence|ordre ne compte|ordre compte|monoton|inconsist|retirer un fait|plusieurs agents|deux experts|l.ordre'),
 ('kr-wumpus', r'wumpus|monstre|caverne|yob'),
 ('kr-first-order', r'premier ordre|datalog|avec variables|quantif|\\forall|indécidab'),
 ('kr-ontologies', r'ontolog|wordnet|rdf|owl|graphe de connaissances|requête|sparql|triplet'),
 ('kr-description-logics', r'logiques? de description|\\mathcal\{alc\}|alc\b|tbox|abox|subsomption|tableau|décidable|profils|hermit|pellet'),
 ('sat-cnf', r'cnf|tseitin|forme normale|circuit'),
 ('sat-resolution', r'résolution\b|résolvante'),
 ('sat-dpll', r'dpll|davis|putnam|dp-60|retours? arrière|élimination de variable'),
 ('sat-cdcl', r'cdcl|apprentissage de clause|clause apprise|conflit|industriel'),
 ('sat-branching', r'vsids|branchement|redémarrage|restart|heuristique de choix'),
 ('sat-local-search', r'gsat|walksat|recherche locale|aléatoire|seuil'),
 ('sat-encoding', r'encodage|encoder|model checking|graphplan|strips|erdős|discrépance|monde du monstre|planification'),
 ('sat-np', r'np\b|np-|polynomial|réduction|classe|preuve|complexité|intractab'),
 ('csp-modeling', r'variables|domaines|contraintes en (in|ex)tension|modéli|cryptarithme|reines|énigme'),
 ('csp-global-constraints', r'alldifferent|globale|\bsum\b|table\b|extension'),
 ('csp-propagation', r'arc.consistan|forward checking|mac\b|anticipation|propagation|filtrage'),
 ('csp-heuristics', r'heuristique|fail.first|dom/wdeg|ordre des variables'),
 ('csp-local-search', r'recherche locale|min.conflicts|claviers'),
 ('csp-ortools', r'or-tools|ortools|pycsp|cp-sat|model\(\)|addallowed'),
 ('csp-applications', r'sudoku|ordonnancement|job.shop|flow.shop|tournées|infirmières|porte-conteneurs|séquencement|carrés magiques|mots croisés|eternity|applications'),
 ('search-formalization', r'formalisation|formulation|états|opérateurs|taquin|reines|cavaliers|dominos|voyageur de commerce|coût des opérateurs|modéliser'),
 ('search-dijkstra', r'dijkstra|coût uniforme'),
 ('search-uninformed', r'aveugle|profondeur|largeur|iterative|bidirectionnelle|mystère|schéma général'),
 ('search-heuristics', r'heuristique|gloutonne|admissib|minima locaux|influences'),
 ('search-a-star', r'a\*|a\\\*|astar'),
 ('search-a-star-proof', r'preuve|admissibilité de a'),
 ('search-variants', r'ida\*|ida\\\*|hpa|mémoire|hiérarch'),
 ('search-local', r'recherche locale|minima locaux|recuit|hill'),
 ('search-genetic', r'génétique|darwin|chromosome|reproduction|mutation|sélection|fitness|roue|tournoi|ogm|hyperparam|karl sims|créatures|sac à dos|biologie'),
 ('search-ants', r'fourmi|phéromone'),
 ('plan-strips', r'strips|monde des blocs|singe|bananes|pile de buts|shrdlu'),
 ('plan-pddl', r'pddl|domaine|substitution|instancier|sémantique du langage|représentation factorisée|roue de secours'),
 ('plan-graphplan', r'graphplan|graphe de planification|mutex'),
 ('plan-sat', r'gsat|walksat|codage sat|formules aléatoires|exploration et exploitation'),
 ('plan-games', r'half-life|f\.e\.a\.r|machines à états|goap|escouade|coût par action|vecteur d.état|armes|temps réel|comportements modulaires|préconditions et effets procéduraux'),
 ('boardgames-minimax', r'minimax|arbre de jeu|arbres de jeu'),
 ('boardgames-alpha-beta', r'alpha|élagage'),
 ('boardgames-evaluation', r'fonction d.évaluation|horizon|coupure'),
 ('boardgames-mcts', r'mcts|monte.carlo|uct'),
 ('boardgames-expectimax', r'expectimax|hasard'),
 ('boardgames-history', r'deep blue|alphago|turbochamp|kasparov|échecs'),
 ('videogames-history', r'pac-man|space invaders|doom|wolfenstein|herzog|midimaze|creatures|battlecruiser|half-life|black and white|left 4 dead|premiers jeux|premiers « bots|où l.ia est|industrie du jeu|de plus en plus'),
 ('videogames-fsm', r'machine à états|machines à états|fsm|état 4|trois règles pour un soldat|langages pour l.ia'),
 ('videogames-scripting', r'scumm|script|systèmes en couches'),
 ('videogames-behavior-trees', r'arbres? de comportement|behavior tree'),
 ('videogames-steering', r'steer|seek|flee|arrive|boïd|boid|reynolds|thon|pursuit|evasion|avoider|follow path|midtown'),
 ('videogames-navigation', r'waypoint|navmesh|navigation mesh|grille|secteurs|praticabilité|hpa|jump point|lisser le chemin|couverture|positions de combat'),
 ('videogames-influence-maps', r'influence|champs de potentiel|killzone|tactique|embuscade|position sûre|points de contact|matrices'),
 ('videogames-cellular-automata', r'jeu de la vie|automate|b3/s23|feu de forêt|percolation|wireworld|turing'),
 ('videogames-llm', r'llm|covert protocol|bloom|inworld|pnj'),
 ('proba-basics', r'loi jointe|indépendance|règle de bayes|bayes à la main|bayes naïf|facteurs de certitude|probabilité comme|règles du jeu|justifications|logique échoue|test médical'),
 ('proba-bayesian-networks', r'réseau bayésien|alarme|factorisation|construire un réseau|tables|où en trouve'),
 ('proba-d-separation', r'd-séparation|explaining away|motifs|indépendances'),
 ('proba-inference', r'requête|énumération|élimination de variables|polytree|jonction|échantillonn|np-difficile|trois voies'),
 ('proba-compilation', r'compil|nnf|dnnf|robdd|diagrammes de décision|circuit arithmétique|comptage|compter les modèles|hiérarchie des langages|cnf pondérée'),
 ('causality-history', r'galton|pearson|wright|cochons|fisher|exil|genèse|pearl|livre'),
 ('causality-ladder', r'échelon|hiérarchie stricte|test de turing|voir|faire|imaginer'),
 ('causality-models', r'modèle causal|:=|graphe d.un modèle|réfuté|briques|chaîne et fourche|collisionneur|d-séparation|médicament|deux graphes'),
 ('causality-intervention', r'interven|\\?do\b|essai randomisé|ajustement|porte arrière|porte avant|simpson|facteur de confusion|prescrire'),
 ('causality-do-calculus', r'do-calcul|complet et décidable'),
 ('causality-counterfactuals', r'contrefactuel|trois étapes|peloton|circuit comme oracle|autre genre'),
 ('causality-ml', r'apprentissage automatique|renforcement|chutzpah|d.où vient le graphe|langage formel de plus|aller plus loin'),
 ('llm-history', r'19[5-9]0|2000-2010|alpac|n-gramme|openai|deepmind|gpt|microsoft|milliard|pause|agi|compute|buzz|chat'),
 ('llm-embeddings', r'embedding|vecteur|dimension|produit scalaire|cosinus|projeter|matriciel|numpy|np\.dot|softmax|glove|word2vec|cbow|negative sampling|sens des mots|wordnet|ontologie|polysémie|queen'),
 ('llm-transformers', r'transformer|attention'),
 ('llm-rag', r'rag\b|graphrag|multimodal'),
 ('llm-agents', r'agent|outils|boucle|mémoire|fenêtre de contexte|fine-tuning|planification|harnais|interaction'),
 ('general-wumpus', r'wumpus|monde du monstre'),
 ('general-sims', r'\bsims\b'),
 ('general-mycin', r'mycin'),
 ('general-chinese-room', r'chambre chinoise|chinese room|searle'),
 ('general-bias', r'biais|compas|équité'),
 ('general-reliability', r'fiab|confiance|garantie|responsab|ai act|parcoursup|explicab|auditable|invérifiable'),
 ('general-demo', r'démo|demo|html|plateau|en blocs|\.html'),
 ('general-lab', r'\btp\b|retour sur le tp|à vous de coder|à vos claviers|à faire'),
 ('general-exercise', r'à vous|à la main|exercice|exercices|au tableau|cahier'),
]
FAMILLES={'rc':['kr-','general-'],'rc-graphes':['kr-','general-'],'sat':['sat-','kr-','general-'],'csp':['csp-','general-'],
 'recherche':['search-','general-'],'planification':['plan-','search-','videogames-','general-'],'proba':['proba-','general-'],
 'causalite':['causality-','proba-','general-'],'jeux':['videogames-','boardgames-','search-','plan-','general-'],'llm':['llm-','kr-','general-'],
 'intro-module':['kr-','sat-','llm-','general-']}
DEF={'csp/01':'csp-modeling','csp/02':'csp-propagation','csp/03':'csp-ortools','csp/04':'csp-applications','csp/05':'csp-global-constraints',
 'jeux/01':'videogames-history','jeux/02':'videogames-steering','jeux/03':'videogames-cellular-automata','jeux/04':'videogames-navigation','jeux/05':'videogames-navigation',
 'jeux/06':'videogames-influence-maps','jeux/07':'videogames-behavior-trees','jeux/08':'boardgames-minimax',
 'llm/01':'llm-history','llm/02':'llm-embeddings','llm/03':'llm-embeddings','llm/04':'llm-embeddings','llm/05':'llm-agents','llm/06':'llm-agents',
 'proba/01':'proba-basics','proba/02':'proba-bayesian-networks','proba/03':'proba-inference','proba/04':'proba-compilation',
 'rc-graphes/01':'kr-first-order','rc/00':'kr-formal-language','rc/01':'kr-rules','rc/02':'kr-horn','rc/03':'kr-negation','rc/04':'general-history',
 'sat/01':'kr-rules','sat/02':'sat-cnf','sat/03':'sat-np','sat/04':'sat-encoding','sat/05':'sat-dpll','sat/06':'sat-cdcl',
 'recherche/01-recherche':'search-formalization','recherche/01-planifier':'plan-strips','recherche/02-genetique':'search-genetic','recherche/02-recherche':'search-uninformed','recherche/03':'search-heuristics','recherche/04':'search-ants',
 'planification/01':'plan-strips','planification/02':'plan-pddl','planification/03':'plan-graphplan','planification/04':'plan-games',
 'causalite/01':'causality-history','causalite/02':'causality-models','causalite/03':'causality-intervention','causalite/04':'causality-counterfactuals',
 'intro-module/00':'general-philosophy','intro-module/01':'kr-agent','intro-module/02':'kr-formal-language','intro-module/03':'sat-np'}
def familles(path):
    d=path.split('/')[1]; return FAMILLES.get(d,['general-'])
def defaut(path):
    rel=path.replace('slides/','').replace('.yaml','')
    for k,v in sorted(DEF.items(), key=lambda kv:-len(kv[0])):
        if rel.startswith(k): return v
    return None
GEN_OK={'general-wumpus','general-sims','general-mycin','general-chinese-room','general-bias','general-reliability','general-demo','general-lab','general-exercise'}
GEN_BODY={'general-wumpus','general-sims','general-mycin','general-chinese-room'}
stats={}; untagged=[]; nb=0
for path in sorted(glob.glob('slides/*/*.yaml')):
    if path.endswith('.questions.yaml'): continue
    fam=familles(path); raw=open(path).read()
    try: slides=yaml.safe_load(raw)
    except Exception as e: print('yaml?',path,e); continue
    if not isinstance(slides,list): continue
    lines=raw.split('\n'); starts=[i for i,l in enumerate(lines) if l.startswith('- ')]
    if len(starts)!=len(slides): print('désalignement',path); continue
    edits=[]   # (ligne, mode, texte)
    for idx,s in enumerate(slides):
        if not isinstance(s,dict) or 'title' not in s or 'tags' in s: continue
        t=texte(s); titre=texte({'t':s.get('title')}); meta=s.get('meta') or {}
        summ=texte({'x':meta['summary']}) if isinstance(meta,dict) and 'summary' in meta else ''
        found=[]
        for tag,rx in R:
            if not any(tag.startswith(f) for f in fam): continue
            if tag.startswith('general-') and tag not in GEN_OK: continue
            if re.search(rx,titre): found.append((tag,3)); continue
            if summ and re.search(rx,summ): found.append((tag,2)); continue
            if len(re.findall(rx,t))>=3 or (tag in GEN_BODY and re.search(rx,t)): found.append((tag,1))
        if s.get('hauteur'): found.append(('general-philosophy',3))
        if s.get('respiration'): found.append(('general-anecdote',2))
        if '/04-histoire' in path: found.append(('general-history',3))
        if isinstance(meta,dict) and re.search(r'à vérifier|a vérifier|à relire|premier jet', str(meta), re.I): found.append(('general-to-check',3))
        if s.get('template')=='cahier': found.append(('general-exercise',3))
        found.sort(key=lambda x:-x[1]); seen=[]
        for tag,w in found:
            if tag not in seen: seen.append(tag)
        tech=[x for x in seen if not x.startswith('general-')][:2]
        gen=[x for x in seen if x.startswith('general-')][:1] if tech else [x for x in seen if x.startswith('general-')][:2]
        tags=tech+gen
        if not tags:
            d=defaut(path)
            if d: tags=[d]; untagged.append((path,titre[:50]))
            else: untagged.append((path,titre[:50])); continue
        for tg in tags: stats[tg]=stats.get(tg,0)+1
        nb+=1
        ln=starts[idx]; txt=f"tags: [{', '.join(tags)}]"
        if lines[ln].startswith('- {'):           # transparent en une ligne : insérer avant l'accolade finale
            j=lines[ln].rstrip().rfind('}'); edits.append((ln,'flow',txt,j))
        else:                                      # insérer avant la prochaine clé de niveau 2, ou à la fin du bloc
            fin=starts[idx+1] if idx+1<len(starts) else len(lines)
            k=None
            for m in range(ln+1,fin):
                if re.match(r'^  [A-Za-z_]+:', lines[m]): k=m; break
            if k is None:
                k=fin
                while k>ln+1 and lines[k-1].strip()=='' : k-=1
            edits.append((k,'block','  '+txt,None))
    for ln,mode,txt,j in sorted(edits, key=lambda e:-e[0]):
        if mode=='flow': l=lines[ln]; lines[ln]=l[:j].rstrip()+', '+txt+l[j:]
        else: lines.insert(ln, txt)
    open(path,'w').write('\n'.join(lines))
print('transparents tagués :', nb, '| par défaut de fichier :', len(untagged))
for k,v in sorted(stats.items(), key=lambda x:-x[1]): print(f'{v:4} {k}')
