"""
Constantes léxicas, morfológicas y taxonómicas para el análisis semántico LSEC (LSEC 2.1.1).

Extraído de `semantic_parser.py` para cumplir con el principio de Responsabilidad Única (SRP).
"""

from __future__ import annotations

from typing import Dict, Set, Tuple

KNOWN_VERB_FORMS: Dict[str, str] = {
    # Formas frecuentes de los videos institucionales 4-10.
    "aprendes": "aprender", "aprende": "aprender", "aprendemos": "aprender",
    "aprendí": "aprender", "aprendió": "aprender",
    "implemento": "implementar", "implementó": "implementar",
    "implementan": "implementar", "implementamos": "implementar",
    "inicio": "iniciar", "inició": "iniciar", "inician": "iniciar",
    "iniciamos": "iniciar", "iniciará": "iniciar",
    "realizamos": "realizar", "realizaremos": "realizar", "realizarán": "realizar",
    "responderá": "responder", "responderán": "responder",
    "revisan": "revisar", "revisamos": "revisar",
    "escríbenos": "escribir", "escribenos": "escribir",
    "inscribirte": "inscribir", "inscríbete": "inscribir", "inscribete": "inscribir",
    "invitarles": "invitar", "invítales": "invitar",
    # preferir (spaCy devuelve el lema truncado "prefier")
    "prefiero": "preferir", "prefieres": "preferir", "prefiere": "preferir",
    "preferimos": "preferir", "preferís": "preferir", "prefieren": "preferir",
    "preferí": "preferir", "preferiste": "preferir", "prefirió": "preferir",
    "prefirieron": "preferir", "prefiriendo": "preferir", "preferido": "preferir",
    # graduar con clítico (spaCy lematiza "graduarnos" como "graduarno")
    "graduarme": "graduar", "graduarte": "graduar", "graduarse": "graduar",
    "graduarnos": "graduar", "graduarlos": "graduar", "graduarlas": "graduar",
    "graduaron": "graduar", "graduando": "graduar", "graduado": "graduar",
    # comer
    "como": "comer", "comes": "comer", "come": "comer", "comemos": "comer", "coméis": "comer", "comen": "comer",
    "comí": "comer", "comiste": "comer", "comió": "comer", "comimos": "comer", "comieron": "comer", "comiendo": "comer", "comido": "comer",
    # beber
    "bebo": "beber", "bebes": "beber", "bebe": "beber", "bebemos": "beber", "bebéis": "beber", "beben": "beber",
    "bebí": "beber", "bebiste": "beber", "bebió": "beber", "bebimos": "beber", "bebieron": "beber", "bebiendo": "beber", "bebido": "beber",
    # comprar
    "compro": "comprar", "compras": "comprar", "compra": "comprar", "compramos": "comprar", "compráis": "comprar", "compran": "comprar",
    "compré": "comprar", "compraste": "comprar", "compró": "comprar", "compraron": "comprar", "comprando": "comprar", "comprado": "comprar",
    # estudiar
    "estudio": "estudiar", "estudias": "estudiar", "estudia": "estudiar", "estudiamos": "estudiar", "estudian": "estudiar",
    "estudié": "estudiar", "estudió": "estudiar", "estudiaron": "estudiar", "estudiando": "estudiar", "estudiado": "estudiar",
    # llegar
    "llego": "llegar", "llegas": "llegar", "llega": "llegar", "llegamos": "llegar", "llegan": "llegar",
    "llegué": "llegar", "llegaste": "llegar", "llegó": "llegar", "llegaron": "llegar", "llegando": "llegar", "llegado": "llegar",
    "llegue": "llegar", "llegues": "llegar", "lleguen": "llegar",
    # ir
    "voy": "ir", "vas": "ir", "va": "ir", "vamos": "ir", "van": "ir", "fui": "ir", "fuiste": "ir", "fueron": "ir", "yendo": "ir", "ido": "ir",
    # venir
    "vengo": "venir", "vienes": "venir", "viene": "venir", "venimos": "venir", "vienen": "venir",
    "vine": "venir", "viniste": "venir", "vino": "venir", "vinimos": "venir", "vinieron": "venir", "viniendo": "venir", "venido": "venir",
    # querer
    "quiero": "querer", "quieres": "querer", "quiere": "querer", "queremos": "querer", "quieren": "querer", "quiso": "querer", "queriendo": "querer", "querido": "querer",
    # poder
    "puedo": "poder", "puedes": "poder", "puede": "poder", "podemos": "poder", "pueden": "poder", "pudo": "poder", "pudieron": "poder",
    # saber
    "sé": "saber", "sabes": "saber", "sabe": "saber", "sabemos": "saber", "saben": "saber", "supe": "saber", "supo": "saber", "supieron": "saber",
    # hacer
    "hago": "hacer", "haces": "hacer", "hace": "hacer", "hacemos": "hacer", "hacen": "hacer", "haz": "hacer", "hizo": "hacer", "hicieron": "hacer", "haciendo": "hacer", "hecho": "hacer",
    # decir
    "digo": "decir", "dices": "decir", "dice": "decir", "decimos": "decir", "dicen": "decir", "dijo": "decir", "dijeron": "decir", "dime": "decir", "dilo": "decir",
    # dar
    "doy": "dar", "das": "dar", "da": "dar", "damos": "dar", "dan": "dar", "di": "dar", "diste": "dar", "dio": "dar", "dimos": "dar", "dieron": "dar",
    "daré": "dar", "darás": "dar", "dará": "dar", "daremos": "dar", "darán": "dar", "dame": "dar", "dale": "dar",
    # ver
    "veo": "ver", "ves": "ver", "ve": "ver", "vemos": "ver", "ven": "ver", "vi": "ver", "viste": "ver", "vio": "ver", "vimos": "ver", "vieron": "ver", "viendo": "ver", "visto": "ver", "verlo": "ver", "verla": "ver", "verte": "ver", "verme": "ver",
    # dejar
    "dejo": "dejar", "dejas": "dejar", "deja": "dejar", "dejamos": "dejar", "dejan": "dejar", "dejé": "dejar", "dejaste": "dejar", "dejó": "dejar", "dejaron": "dejar", "dejando": "dejar", "dejado": "dejar",
    "dejaré": "dejar", "dejarás": "dejar", "dejará": "dejar", "dejaremos": "dejar", "dejarán": "dejar",
    # llevar
    "llevo": "llevar", "llevas": "llevar", "lleva": "llevar", "llevamos": "llevar", "llevan": "llevar", "llevé": "llevar", "llevaste": "llevar", "llevó": "llevar", "llevaron": "llevar", "llevando": "llevar", "llevado": "llevar",
    "llevaré": "llevar", "llevarás": "llevar", "llevará": "llevar", "llevaremos": "llevar", "llevarán": "llevar",
    # entregar
    "entrego": "entregar", "entregas": "entregar", "entrega": "entregar", "entregamos": "entregar", "entregan": "entregar",
    "entregué": "entregar", "entregaste": "entregar", "entregó": "entregar", "entregaron": "entregar", "entregando": "entregar", "entregado": "entregar",
    "entregaré": "entregar", "entregarás": "entregar", "entregará": "entregar", "entregaremos": "entregar", "entregarán": "entregar",
    "entrégalo": "entregar", "entregalo": "entregar", "entrégala": "entregar", "entrégame": "entregar", "entréganoslo": "entregar",
    # avisar
    "aviso": "avisar", "avisas": "avisar", "avisa": "avisar", "avisamos": "avisar", "avisan": "avisar",
    "avisé": "avisar", "avisaste": "avisar", "avisó": "avisar", "avisaron": "avisar", "avisando": "avisar", "avisado": "avisar",
    "avisaré": "avisar", "avisarás": "avisar", "avisará": "avisar", "avisaremos": "avisar", "avisarán": "avisar",
    "avísame": "avisar", "avisame": "avisar", "avísanos": "avisar", "avísale": "avisar",
    # ayudar
    "ayudo": "ayudar", "ayudas": "ayudar", "ayuda": "ayudar", "ayudamos": "ayudar", "ayudan": "ayudar",
    "ayudé": "ayudar", "ayudaste": "ayudar", "ayudó": "ayudar", "ayudaron": "ayudar", "ayudando": "ayudar", "ayudado": "ayudar",
    "ayudaré": "ayudar", "ayudarás": "ayudar", "ayudará": "ayudar", "ayudaremos": "ayudar", "ayudarán": "ayudar",
    "ayúdame": "ayudar", "ayudame": "ayudar", "ayúdanos": "ayudar", "ayúdale": "ayudar",
    # necesitar
    "necesito": "necesitar", "necesitas": "necesitar", "necesita": "necesitar", "necesitamos": "necesitar", "necesitan": "necesitar",
    "necesité": "necesitar", "necesitaste": "necesitar", "necesitó": "necesitar", "necesitaron": "necesitar", "necesitando": "necesitar", "necesitado": "necesitar",
    "necesitaré": "necesitar", "necesitarás": "necesitar", "necesitará": "necesitar", "necesitaremos": "necesitar", "necesitarán": "necesitar",
    # mandar
    "mando": "mandar", "mandas": "mandar", "manda": "mandar", "mandamos": "mandar", "mandan": "mandar",
    "mandé": "mandar", "mandaste": "mandar", "mandó": "mandar", "mandaron": "mandar", "mandando": "mandar", "mandado": "mandar",
    "mandaré": "mandar", "mandarás": "mandar", "mandará": "mandar", "mandaremos": "mandar", "mandarán": "mandar",
    # caminar
    "caminas": "caminar", "camina": "caminar", "caminamos": "caminar", "caminan": "caminar",
    "caminé": "caminar", "caminaste": "caminar", "caminó": "caminar", "caminaron": "caminar", "caminando": "caminar", "caminado": "caminar",
    "caminaré": "caminar", "caminarás": "caminar", "caminará": "caminar", "caminaremos": "caminar", "caminarán": "caminar",
    # viajar
    "viajo": "viajar", "viajas": "viajar", "viaja": "viajar", "viajamos": "viajar", "viajan": "viajar",
    "viajé": "viajar", "viajaste": "viajar", "viajó": "viajar", "viajaron": "viajar", "viajando": "viajar", "viajado": "viajar",
    "viajaré": "viajar", "viajarás": "viajar", "viajará": "viajar", "viajaremos": "viajar", "viajarán": "viajar",
    # trabajar (nota: 'trabajo' es homógrafo nominal)
    "trabajas": "trabajar", "trabaja": "trabajar", "trabajamos": "trabajar", "trabajan": "trabajar",
    "trabajé": "trabajar", "trabajaste": "trabajar", "trabajó": "trabajar", "trabajaron": "trabajar", "trabajando": "trabajar", "trabajado": "trabajar",
    "trabajaré": "trabajar", "trabajarás": "trabajar", "trabajará": "trabajar", "trabajaremos": "trabajar", "trabajarán": "trabajar",
    # visitar / revisar / aprobar
    "visito": "visitar", "visitas": "visitar", "visita": "visitar", "visitamos": "visitar", "visitan": "visitar",
    "visité": "visitar", "visitaste": "visitar", "visitó": "visitar", "visitaron": "visitar", "visitando": "visitar", "visitado": "visitar",
    "visitaré": "visitar", "visitarás": "visitar", "visitará": "visitar", "visitaremos": "visitar", "visitarán": "visitar",
    "reviso": "revisar", "revisas": "revisar", "revisa": "revisar", "revisamos": "revisar", "revisan": "revisar",
    "revisé": "revisar", "revisaste": "revisar", "revisó": "revisar", "revisaron": "revisar", "revisando": "revisar", "revisado": "revisar",
    "revisaré": "revisar", "revisarás": "revisar", "revisará": "revisar", "revisaremos": "revisar", "revisarán": "revisar",
    "apruebo": "aprobar", "apruebas": "aprobar", "aprueba": "aprobar", "aprobamos": "aprobar", "aprueban": "aprobar",
    "aprobé": "aprobar", "aprobaste": "aprobar", "aprobó": "aprobar", "aprobaron": "aprobar", "aprobando": "aprobar", "aprobado": "aprobar",
    "aprobaré": "aprobar", "aprobarás": "aprobar", "aprobará": "aprobar", "aprobaremos": "aprobar", "aprobarán": "aprobar",
    # salir / traer / tener / vivir / leer / dormir / llover / gustar / asistir / mentir / terminar / calmar
    "salgo": "salir", "sales": "salir", "sale": "salir", "salimos": "salir", "salen": "salir", "salí": "salir", "saliste": "salir", "salió": "salir", "salieron": "salir",
    "traigo": "traer", "traes": "traer", "trae": "traer", "traemos": "traer", "traen": "traer", "traje": "traer", "trajo": "traer", "trajeron": "traer",
    "tengo": "tener", "tienes": "tener", "tiene": "tener", "tenemos": "tener", "tienen": "tener", "tuve": "tener", "tuvo": "tener", "tuvieron": "tener",
    "vivo": "vivir", "vives": "vivir", "vive": "vivir", "vivimos": "vivir", "viven": "vivir", "viví": "vivir", "vivió": "vivir", "vivieron": "vivir",
    "leo": "leer", "lees": "leer", "lee": "leer", "leemos": "leer", "leen": "leer", "leí": "leer", "leyó": "leer", "leyeron": "leer",
    "duermo": "dormir", "duermes": "dormir", "duerme": "dormir", "dormimos": "dormir", "duermen": "dormir", "dormí": "dormir", "durmió": "dormir",
    "llueve": "llover", "llovió": "llover", "lloviendo": "llover",
    "gusta": "gustar", "gustan": "gustar", "gustó": "gustar", "gustaron": "gustar",
    "asisto": "asistir", "asistes": "asistir", "asiste": "asistir", "asistimos": "asistir", "asisten": "asistir", "asistí": "asistir", "asistió": "asistir",
    "miento": "mentir", "mientes": "mentir", "miente": "mentir", "mentimos": "mentir", "mienten": "mentir",
    "termino": "terminar", "terminas": "terminar", "termina": "terminar", "terminamos": "terminar", "terminan": "terminar", "termine": "terminar", "terminó": "terminar",
    "termines": "terminar", "terminen": "terminar", "terminemos": "terminar",
    # Formas de subjuntivo, pretérito y futuro de alta frecuencia
    "elegiste": "elegir", "elegimos": "elegir",
    "aprendas": "aprender", "aprenda": "aprender", "aprendamos": "aprender", "aprendan": "aprender",
    "esperes": "esperar", "espere": "esperar", "esperemos": "esperar", "esperen": "esperar",
    "podré": "poder", "podrás": "poder", "podrá": "poder", "podremos": "poder", "podréis": "poder", "podrán": "poder",
    "podría": "poder", "podrías": "poder", "podríamos": "poder", "podríais": "poder", "podrían": "poder",
    "cayó": "caer", "cayeron": "caer", "caía": "caer", "caían": "caer",
    "calma": "calmar", "calme": "calmar", "calman": "calmar",
    # hablar / enseñar / preguntar / llamar / esperar / escuchar / buscar / encontrar / perder / olvidar / pagar / abrir / cerrar / empezar
    "hablo": "hablar", "hablas": "hablar", "habla": "hablar", "hablamos": "hablar", "hablan": "hablar", "hablé": "hablar", "habló": "hablar",
    "enseño": "enseñar", "enseñas": "enseñar", "enseña": "enseñar", "enseñamos": "enseñar", "enseñan": "enseñar", "enseñó": "enseñar",
    "pregunto": "preguntar", "preguntas": "preguntar", "pregunta": "preguntar", "preguntamos": "preguntar", "preguntan": "preguntar", "preguntó": "preguntar",
    "llamo": "llamar", "llamas": "llamar", "llama": "llamar", "llamamos": "llamar", "llaman": "llamar", "llamé": "llamar", "llamó": "llamar",
    "espero": "esperar", "esperas": "esperar", "espera": "esperar", "esperamos": "esperar", "esperan": "esperar", "espérame": "esperar",
    "escucho": "escuchar", "escuchas": "escuchar", "escucha": "escuchar", "escuchamos": "escuchar", "escuchan": "escuchar", "escúchame": "escuchar",
    "busco": "buscar", "buscas": "buscar", "busca": "buscar", "buscamos": "buscar", "buscan": "buscar", "busqué": "buscar", "buscó": "buscar",
    "encuentro": "encontrar", "encuentras": "encontrar", "encuentra": "encontrar", "encontramos": "encontrar", "encuentran": "encontrar", "encontré": "encontrar", "encontró": "encontrar",
    "pierdo": "perder", "pierdes": "perder", "pierde": "perder", "perdemos": "perder", "pierden": "perder", "perdí": "perder", "perdió": "perder",
    "olvido": "olvidar", "olvidas": "olvidar", "olvida": "olvidar", "olvidamos": "olvidar", "olvidan": "olvidar", "olvidé": "olvidar", "olvidó": "olvidar",
    "pago": "pagar", "pagas": "pagar", "paga": "pagar", "pagamos": "pagar", "pagan": "pagar", "pagué": "pagar", "pagó": "pagar",
    "abro": "abrir", "abres": "abrir", "abre": "abrir", "abrimos": "abrir", "abren": "abrir", "abrí": "abrir", "abrió": "abrir",
    "cierro": "cerrar", "cierras": "cerrar", "cierra": "cerrar", "cerramos": "cerrar", "cierran": "cerrar", "cerré": "cerrar", "cerró": "cerrar",
    "empiezo": "empezar", "empiezas": "empezar", "empieza": "empezar", "empezamos": "empezar", "empiezan": "empezar", "empecé": "empezar", "empezó": "empezar",
    "conozco": "conocer", "conoces": "conocer", "conoce": "conocer", "conocemos": "conocer", "conocen": "conocer", "conocí": "conocer", "conoció": "conocer",
    "entiendo": "entender", "entiendes": "entender", "entiende": "entender", "entendemos": "entender", "entienden": "entender", "entendí": "entender", "entendió": "entender",
    # decidir / elegir
    "decido": "decidir", "decides": "decidir", "decide": "decidir", "decidimos": "decidir", "deciden": "decidir", "decidí": "decidir", "decidió": "decidir",
    "elijo": "elegir", "eliges": "elegir", "elige": "elegir", "elegimos": "elegir", "eligen": "elegir", "elegí": "elegir", "eligiste": "elegir", "eligió": "elegir", "eligieron": "elegir", "eligiendo": "elegir", "elegido": "elegir", "elegir": "elegir",
    # salvar / atender / postular / explicar / inaugurar / etc.
    "salvas": "salvar", "salva": "salvar", "salvamos": "salvar", "salvan": "salvar", "salvé": "salvar", "salvó": "salvar",
    "atiendes": "atender", "atiende": "atender", "atendemos": "atender", "atienden": "atender",
    "postular": "postular", "postula": "postular", "explico": "explicar", "explicas": "explicar", "explica": "explicar", "explicamos": "explicar", "explican": "explicar", "explícame": "explicar", "explícaselo": "explicar",
    "inaugurar": "inaugurar", "inauguramos": "inaugurar", "matricularon": "matricular",
    "transformar": "transformar", "transformamos": "transformar", "educamos": "educar", "formamos": "formar",
    "preparamos": "preparar", "evoluciona": "evolucionar", "ofrecemos": "ofrecer", "ofrece": "ofrecer",
    "crean": "crear", "creo": "creer", "crees": "creer", "cree": "creer", "creen": "creer", "construyen": "construir", "construye": "construir",
    "liberan": "liberar", "lideran": "liderar",
    # invitar / formar / inscribir / participar / comunicar
    "invito": "invitar", "invitas": "invitar", "invita": "invitar", "invitamos": "invitar", "invitan": "invitar",
    "invité": "invitar", "invitó": "invitar", "invitaron": "invitar", "invitando": "invitar", "invitado": "invitar",
    "formo": "formar", "formas": "formar", "forma": "formar", "forman": "formar", "formando": "formar", "formado": "formar",
    "inscribo": "inscribir", "inscribes": "inscribir", "inscribe": "inscribir", "inscribimos": "inscribir", "inscriben": "inscribir",
    "inscribirse": "inscribir", "inscríbete": "inscribir", "inscribirte": "inscribir",
    "participo": "participar", "participas": "participar", "participa": "participar", "participamos": "participar", "participan": "participar",
    "comunico": "comunicar", "comunicas": "comunicar", "comunica": "comunicar", "comunicamos": "comunicar", "comunican": "comunicar",
    "comunícate": "comunicar", "comunicate": "comunicar", "comunicarse": "comunicar", "comunicarte": "comunicar",
    "contáctate": "contactar", "contactate": "contactar", "contactarse": "contactar", "contactar": "contactar",
    "regístrate": "registrar", "registrate": "registrar", "registrarse": "registrar",
    "infórmate": "informar", "informate": "informar", "informarse": "informar",
    "acércate": "acercar", "acercate": "acercar", "acercarse": "acercar",
    "matricúlate": "matricular", "matriculate": "matricular", "matricularse": "matricular",
    "prepárate": "preparar", "preparate": "preparar", "prepararse": "preparar",
    # oler / sentir / doler / gustar / cuidar
    "huelo": "oler", "hueles": "oler", "huele": "oler", "olemos": "oler", "huelen": "oler", "oler": "oler",
    "duelo": "doler", "dueles": "doler", "duele": "doler", "duelen": "doler", "dolió": "doler",
    "cuido": "cuidar", "cuidas": "cuidar", "cuida": "cuidar", "cuidamos": "cuidar", "cuidan": "cuidar", "cuidó": "cuidar",
}

NOMINAL_HOMOGRAPHS: Set[str] = {
    "dibujo", "música", "danza", "cine", "teatro", "pintura", "arte", "artes",
    "taller", "talleres", "club", "clubes", "correo", "whatsapp", "parte", "grado",
    "lugar", "lugares", "hogar", "hogares", "mujer", "mujeres", "celular", "celulares",
    "mar", "par", "líder", "líderes", "placer", "carácter", "escolar", "familiar", "popular",
    "ruido", "estado", "lado", "cuidado", "resultado", "sentido", "sonido", "partido",
    "vestido", "contenido", "pedido", "mercado", "chocolate", "chocolates", "tomate", "tomates",
    "aguacate", "aguacates", "combate", "debate", "empate", "rescate", "pescado", "pescados",
    "helado", "helados", "enfermo", "enferma", "enfermos", "enfermas", "cansado", "cansada",
}

POS_GATED_LEMMAS: Set[str] = {
    "como",
    "pregunta", "preguntas",
    "sobre", "entre", "para", "bajo",
}

COPULA_FORMS: Set[str] = {
    "ser", "soy", "eres", "es", "somos", "son", "era", "eras", "éramos", "eran", "fue", "fueron", "sido",
    "estar", "estoy", "estás", "está", "estamos", "están", "estaba", "estaban", "estuvo", "estuvieron", "estado",
    "haber", "hay", "había", "hubo", "habrá", "he", "has", "ha", "hemos", "han",
}

NON_ENCLITIC_WORDS: Set[str] = {
    "película", "películas", "cédula", "cédulas", "fórmula", "fórmulas", "matrícula", "matrículas",
    "cápsula", "cláusula", "mayúscula", "minúscula", "título", "títulos", "artículo", "artículos",
    "capítulo", "capítulos", "módulo", "módulos", "vehículo", "vehículos", "obstáculo", "obstáculos",
    "espectáculo", "espectáculos", "vínculo", "vínculos", "círculo", "círculos", "cálculo", "cálculos",
    "símbolo", "símbolos", "estímulo", "estímulos", "escándalo", "escándalos", "currículo", "miércoles", "árboles",
    "ángeles", "jóvenes", "exámenes", "imágenes", "trámite", "trámites", "límite", "límites", "intérprete", "intérpretes",
    "satélite", "satélites", "cómplice", "cómplices", "aristóteles",
    "fuerte", "fuertes", "suerte", "muerte", "inerte", "norte", "corte", "deporte", "transporte",
    "pasaporte", "soporte", "reporte", "importe", "aporte", "recorte",
}

IRREGULAR_ENCLITIC_MAP: Dict[str, Tuple[str, str]] = {
    "dime": ("decir", "me"), "dilo": ("decir", "lo"), "dila": ("decir", "la"),
    "dile": ("decir", "le"), "diles": ("decir", "les"), "dinos": ("decir", "nos"),
    "dímelo": ("decir", "me"), "dígalo": ("decir", "lo"), "dígame": ("decir", "me"),
    "dame": ("dar", "me"), "dalo": ("dar", "lo"), "dala": ("dar", "la"),
    "dale": ("dar", "le"), "dales": ("dar", "les"), "danos": ("dar", "nos"),
    "dámelo": ("dar", "me"), "déselo": ("dar", "se"), "déme": ("dar", "me"),
    "hazme": ("hacer", "me"), "hazlo": ("hacer", "lo"), "hazla": ("hacer", "la"),
    "hazle": ("hacer", "le"), "hágalo": ("hacer", "lo"), "hágame": ("hacer", "me"),
    "ponme": ("poner", "me"), "ponlo": ("poner", "lo"), "ponla": ("poner", "la"),
    "ponle": ("poner", "le"), "póngalo": ("poner", "lo"), "póngame": ("poner", "me"),
    "tenme": ("tener", "me"), "tenlo": ("tener", "lo"), "tenla": ("tener", "la"),
    "tenle": ("tener", "le"), "téngalo": ("tener", "lo"),
    "vete": ("ir", "te"), "vámonos": ("ir", "nos"), "váyase": ("ir", "se"),
    "tráeme": ("traer", "me"), "tráelo": ("traer", "lo"), "tráela": ("traer", "la"),
    "tráigame": ("traer", "me"), "tráigalo": ("traer", "lo"),
    "óyeme": ("oír", "me"), "mírame": ("mirar", "me"), "míralo": ("mirar", "lo"),
    # El regex genérico de imperativos producía la base truncada "pider".
    "pídeselo": ("pedir", "selo"), "pideselo": ("pedir", "selo"),
    "pídesela": ("pedir", "sela"), "pidesela": ("pedir", "sela"),
    "pídemelo": ("pedir", "melo"), "pidemelo": ("pedir", "melo"),
    "pídeselos": ("pedir", "selos"), "pídeselas": ("pedir", "selas"),
}

IRREGULAR_FUTURE_STEMS: Dict[str, str] = {
    "tendr": "tener", "vendr": "venir", "pondr": "poner", "saldr": "salir",
    "valdr": "valer", "podr": "poder", "sabr": "saber", "habr": "haber",
    "querr": "querer", "har": "hacer", "dir": "decir",
}

PERSON_1_FORMS: Tuple[str, ...] = (
    "como", "bebo", "compro", "estudio", "llego", "voy", "vengo", "quiero", "puedo", "sé", "hago", "digo",
    "doy", "veo", "dejo", "llevo", "entrego", "aviso", "ayudo", "necesito", "mando", "viajo", "visito",
    "reviso", "apruebo", "salgo", "traigo", "tengo", "vivo", "leo", "duermo", "asisto", "miento", "termino",
    "hablo", "enseño", "pregunto", "llamo", "espero", "escucho", "busco", "encuentro", "pierdo", "olvido",
    "pago", "abro", "cierro", "empiezo", "conozco", "entiendo", "decido", "elijo", "invito", "formo",
    "inscribo", "participo", "comunico", "explico", "trabajo", "soy", "estoy", "he",
    "comí", "bebí", "compré", "estudié", "llegué", "fui", "vine", "supe", "di", "vi", "dejé", "llevé",
    "entregué", "avisé", "ayudé", "necesité", "mandé", "caminé", "viajé", "trabajé", "visité", "revisé",
    "aprobé", "salí", "traje", "tuve", "viví", "leí", "dormí", "asistí", "hablé", "llamé", "busqué",
    "encontré", "perdí", "olvidé", "pagué", "abrí", "cerré", "empecé", "conocí", "entendí", "decidí",
    "elegí", "salvé", "invité", "daré", "mandaré", "viajaré", "aprobaré", "empezaré", "trabajaba",
)

PERSON_2_FORMS: Tuple[str, ...] = (
    "comes", "bebes", "compras", "estudias", "llegas", "llegues", "vas", "vienes", "quieres", "puedes",
    "sabes", "haces", "dices", "das", "ves", "dejas", "llevas", "entregas", "avisas", "ayudas", "necesitas",
    "mandas", "caminas", "viajas", "trabajas", "visitas", "revisas", "apruebas", "sales", "traes", "tienes",
    "vives", "lees", "duermes", "asistes", "mientes", "terminas", "hablas", "enseñas", "preguntas", "llamas",
    "esperas", "escuchas", "buscas", "encuentras", "pierdes", "olvidas", "pagas", "abres", "cierras",
    "empiezas", "conoces", "entiendes", "decides", "eliges", "salvas", "atiendes", "explicas", "invitas",
    "formas", "inscribes", "participas", "comunicas",
    "haz", "di", "ve", "ten", "ven", "pon", "sal", "dime", "dame", "dale",
    "comiste", "bebiste", "compraste", "llegaste", "fuiste", "viniste", "diste", "viste", "dejaste",
    "llevaste", "entregaste", "avisaste", "ayudaste", "necesitaste", "mandaste", "caminaste", "viajaste",
    "trabajaste", "visitaste", "revisaste", "aprobaste", "saliste", "viviste", "dormiste", "hablaste",
    "enseñaste", "preguntaste", "llamaste", "elegiste",
    "darás", "mandarás",
    "comunícate", "comunicate", "inscríbete", "inscribete", "regístrate", "infórmate",
    "avísame", "avisame", "ayúdame", "ayudame", "entrégalo", "entregalo", "explícame",
)

PERSON_3_FORMS: Tuple[str, ...] = (
    "come", "bebe", "compra", "estudia", "llega", "va", "viene", "quiere", "puede", "sabe", "hace", "dice",
    "da", "deja", "lleva", "entrega", "avisa", "ayuda", "necesita", "manda", "camina", "viaja", "trabaja",
    "visita", "revisa", "aprueba", "sale", "trae", "tiene", "vive", "lee", "duerme", "llueve", "gusta",
    "asiste", "miente", "termina", "termine", "calma", "calme", "habla", "enseña", "pregunta", "llama",
    "espera", "escucha", "busca", "encuentra", "pierde", "olvida", "paga", "abre", "cierra", "empieza",
    "conoce", "entiende", "decide", "elige", "salva", "atiende", "postula", "explica", "evoluciona",
    "ofrece", "cree", "construye", "invita", "forma", "inscribe", "participa", "comunica",
    "comió", "bebió", "compró", "estudió", "llegó", "vino", "quiso", "pudo", "supo", "hizo", "dijo", "dio",
    "vio", "dejó", "llevó", "entregó", "avisó", "ayudó", "necesitó", "mandó", "caminó", "viajó", "trabajó",
    "visitó", "revisó", "aprobó", "salió", "trajo", "tuvo", "vivió", "leyó", "durmió", "llovió", "gustó",
    "asistió", "terminó", "habló", "enseñó", "preguntó", "llamó", "buscó", "encontró", "perdió", "olvidó",
    "pagó", "abrió", "cerró", "empezó", "conoció", "entendió", "decidió", "eligió", "salvó", "invitó",
    "dará", "mandará",
)

PERSON_1_PL_FORMS: Tuple[str, ...] = (
    "comemos", "bebemos", "compramos", "estudiamos", "llegamos", "vamos", "venimos", "queremos", "podemos",
    "sabemos", "hacemos", "decimos", "damos", "vemos", "dejamos", "llevamos", "entregamos", "avisamos",
    "ayudamos", "necesitamos", "mandamos", "caminamos", "viajamos", "trabajamos", "visitamos", "revisamos",
    "aprobamos", "salimos", "traemos", "tenemos", "vivimos", "leemos", "dormimos", "asistimos", "mentimos",
    "terminamos", "hablamos", "enseñamos", "preguntamos", "llamamos", "esperamos", "escuchamos", "buscamos",
    "encontramos", "perdemos", "olvidamos", "pagamos", "abrimos", "cerramos", "empezamos", "conocemos",
    "entendemos", "decidimos", "elegimos", "comimos", "bebimos", "educamos", "formamos", "preparamos",
    "invitamos", "inscribimos", "participamos", "comunicamos", "explicamos", "inauguramos", "transformamos",
    "ofrecemos", "daremos", "mandaremos",
)

PERSON_3_PL_FORMS: Tuple[str, ...] = (
    "comen", "beben", "compran", "estudian", "llegan", "van", "vienen", "quieren", "pueden", "saben",
    "hacen", "dicen", "dan", "ven", "dejan", "llevan", "entregan", "avisan", "ayudan", "necesitan",
    "mandan", "caminan", "viajan", "trabajan", "visitan", "revisan", "aprueban", "salen", "traen", "tienen",
    "viven", "leen", "duermen", "gustan", "asisten", "mienten", "terminan", "calman", "hablan", "enseñan",
    "preguntan", "llaman", "esperan", "escuchan", "buscan", "encuentran", "pierden", "olvidan", "pagan",
    "abren", "cierran", "empiezan", "conocen", "entienden", "deciden", "eligen", "salvan", "atienden",
    "explican", "crean", "construyen", "liberan", "lideran", "invitan", "forman", "inscriben", "participan",
    "comunican",
    "comieron", "bebieron", "compraron", "estudiaron", "llegaron", "fueron", "vinieron", "pudieron",
    "supieron", "hicieron", "dijeron", "dieron", "vieron", "dejaron", "llevaron", "entregaron", "avisaron",
    "ayudaron", "necesitaron", "mandaron", "caminaron", "viajaron", "trabajaron", "visitaron", "revisaron",
    "aprobaron", "salieron", "trajeron", "tuvieron", "vivieron", "leyeron", "gustaron", "hablaron",
    "enseñaron", "preguntaron", "llamaron", "eligieron", "matricularon", "invitaron",
    "darán", "mandarán",
)

FORBIDDEN_PREDICATE_LEMMAS: Set[str] = {
    "yo", "tú", "tu", "él", "ella", "ello", "nosotros", "nosotras", "ustedes", "ellos", "ellas",
    "me", "te", "se", "nos", "les", "le", "mi", "mis", "tus", "su", "sus",
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "qué", "que", "quién", "quien", "quiénes", "quienes", "dónde", "donde", "cuándo", "cuando", "cómo", "como",
    "por qué", "para qué", "cuál", "cual", "cuáles", "cuales",
    "manzana", "manzanas", "carne", "carnes", "pan", "panes", "agua", "aguas", "libro", "casa",
    "dibujo", "música", "danza", "cine", "teatro", "pintura", "arte", "artes", "taller", "club", "correo", "whatsapp",
    "pesar", "cabo", "embargo", "obstante", "favor", "gracias",
}

CONSUMABLE_NOUNS: Set[str] = {
    "manzana", "manzanas", "carne", "carnes", "pan", "panes", "agua", "aguas", "comida", "fruta", "alimento"
}

LOCATION_NOUNS: Set[str] = {
    "escuela", "hospital", "universidad", "campus", "sede", "laboratorio", "aula", "clase", "casa"
}

PERSON_NOUNS: Set[str] = {
    "estudiante", "estudiantes", "profesor", "profesores", "profesional", "profesionales",
    "seres humanos", "persona", "personas", "médico", "médicos", "técnicos", "ciudadanos", "maría", "juan", "pedro",
    "niño", "niños", "niña", "niñas", "hermano", "hermanos", "hermana", "hermanas",
    "mamá", "madre", "papá", "padre", "padres", "hijo", "hijos", "hija", "hijas",
    "abuelo", "abuelos", "abuela", "abuelas", "familia", "amigo", "amigos", "amiga", "amigas",
    "compañero", "compañeros", "coordinador", "coordinadora", "director", "directora",
    "paciente", "pacientes", "enfermera", "enfermero", "doctor", "doctora", "joven", "jóvenes",
    "perro", "perros", "gato", "gatos",
}

DEFAULT_PRONOUN_DEIXIS: Dict[str, str] = {
    "yo": "PRO1", "me": "PRO1", "mí": "PRO1", "conmigo": "PRO1",
    "tú": "PRO2", "te": "PRO2", "ti": "PRO2", "contigo": "PRO2", "usted": "PRO2",
    "él": "PRO3", "ella": "PRO3",
    "nosotros": "PRO1-PL", "nos": "PRO1-PL", "nosotras": "PRO1-PL",
    "ustedes": "PRO2-PL", "ellos": "PRO3-PL", "ellas": "PRO3-PL",
}
