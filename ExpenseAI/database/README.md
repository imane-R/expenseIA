# Base de données PostgreSQL ExpenseAI

PostgreSQL constitue la couche persistante de ExpenseAI. Il stocke les lignes de
dépenses normalisées, alimente les futures analyses et fournit une structure stable
pour la future application Streamlit et les prédictions du modèle.

Cette étape ne réalise aucun entraînement de Machine Learning et n'utilise pas
Docker.

## Structure des tables

### `expense_types`

Référentiel des types de dépenses. Chaque nom est unique et une dépense référence
obligatoirement un type.

### `projects`

Référentiel des codes projets réels. La valeur technique `SANS_PROJET` du CSV n'est
jamais insérée dans cette table : une dépense sans projet possède `project_id = NULL`.

### `expenses`

Table centrale au niveau de la **ligne de dépense**. Elle conserve le groupe de la
note de frais, la date, le type, le montant TTC, le caractère facturable, le projet
éventuel, le taux de taxe et la cible observée.

La contrainte `target IN (0, 1)` garantit la convention suivante :

- `0` : ligne approuvée ;
- `1` : ligne refusée.

### `predictions`

Table réservée aux futures prédictions. Une prédiction peut référencer une dépense
existante, mais cette relation est optionnelle afin de permettre plus tard une
prédiction sur une nouvelle saisie. Les contraintes garantissent une classe dans
`{0, 1}` et une probabilité comprise entre 0 et 1.

### `staging_expenses_raw`

Zone brute temporaire destinée à la traçabilité de l'Excel, à la comparaison entre
structure source et structure normalisée, et aux benchmarks. Ses colonnes métier
sont en `TEXT` pour préserver la valeur reçue avant conversion.

Cette table ne doit jamais être interrogée directement par Streamlit. Le script
`load_staging.py` l'alimente directement depuis la feuille `data` du fichier Excel,
sans nettoyage métier. La contrainte `(source_file, source_row_number)` permet de
réexécuter l'import sans dupliquer les lignes brutes.

## Pipeline de données

```text
Excel brut ──► staging_expenses_raw ──► compréhension et traçabilité
     │
     └───────► notebook de preprocessing ──► expenses_clean.csv
                                             │
                                             ▼
                         tables normalisées ──► v_ml_expenses
```

Le pipeline logique est **Excel brut → staging → preprocessing → tables
normalisées → vue ML**. Dans l'implémentation actuelle, le notebook de preprocessing
lit encore directement le même Excel original et produit le CSV nettoyé ; la
staging reste une copie de traçabilité et de benchmark, et non une source utilisée
par Streamlit ou par le futur modèle. Cette séparation évite qu'une transformation
ML modifie la représentation brute.

## Relations

```text
expense_types 1 ──────── n expenses n ──────── 0..1 projects
                              │
                              └──────── 1 ──────── n predictions
                                        relation optionnelle côté prediction
```

La suppression d'un type utilisé est bloquée. Si un projet ou une dépense est
supprimé, les clés étrangères optionnelles correspondantes sont mises à `NULL`.

## Vue Machine Learning

`v_ml_expenses` reconstruit les variables lisibles du futur dataset ML : type,
montant TTC, statut facturable, code projet, taux de taxe et variables temporelles.
Elle transforme un `project_id` nul en `SANS_PROJET` avec `COALESCE` et reproduit la
convention `jour_semaine` utilisée par pandas : lundi = 0, dimanche = 6.

La vue n'entraîne aucun modèle et ne remplace pas le futur pipeline scikit-learn.

## Index

Quatre index ciblés sont créés sur :

- `expenses.expense_group` pour retrouver les lignes d'une note ;
- `expenses.expense_date` pour les filtres temporels ;
- `expenses.expense_type_id` pour les jointures par type ;
- `expenses.project_id` pour les jointures et filtres par projet.

`target` ne reçoit pas d'index classique par défaut. Il ne possède que deux
modalités et la classe refusée est très minoritaire ; la pertinence d'un index
classique ou partiel doit être décidée à partir de requêtes réelles et de
`EXPLAIN ANALYZE`.

## Prérequis manuels

PostgreSQL et l'outil `psql` doivent être installés et démarrés par l'utilisateur.
Le projet ne les installe pas et ne suppose pas qu'un serveur existe déjà.

Depuis la racine de `ExpenseAI`, créer l'environnement local si nécessaire :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Créer la configuration locale :

```bash
cp .env.example .env
```

Compléter `.env` sans jamais le versionner :

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=expenseai
DB_USER=votre_utilisateur
DB_PASSWORD=votre_mot_de_passe
```

## Création de la base

La création de la base nécessite un rôle PostgreSQL autorisé. Exemple à adapter à
votre installation :

```bash
createdb -h localhost -p 5432 -U votre_utilisateur expenseai
```

Cette commande est manuelle : son succès dépend de l'installation, du serveur et
des droits locaux.

## Initialisation du schéma

`psql` utilise les variables `PG*`. Elles peuvent être définies à partir des mêmes
valeurs que `.env`, sans placer le mot de passe dans une commande ou dans Git :

```bash
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=expenseai
export PGUSER=votre_utilisateur
export PGPASSWORD='votre_mot_de_passe'
psql -v ON_ERROR_STOP=1 -f database/schema.sql
unset PGPASSWORD
```

Le script est réexécutable : il utilise `IF NOT EXISTS` pour les tables et index,
et `CREATE OR REPLACE VIEW` pour la vue.

## Test de la connexion SQLAlchemy

Après configuration de `.env` :

```bash
python -m database.connection
```

La commande retourne un code non nul si `.env` est incomplet, si PostgreSQL n'est
pas démarré ou si la base n'est pas accessible. Aucun mot de passe n'est affiché.

## Import de l'Excel brut dans la staging

Après l'initialisation du schéma, charger d'abord les 7 071 lignes originales :

```bash
python -m database.load_staging
```

Le chargeur :

1. ouvre le classeur en lecture seule et utilise la feuille `data` ;
2. valide les 14 en-têtes et les 7 071 lignes de données ;
3. utilise le numéro de ligne Excel réel, de 2 à 7 072 ;
4. conserve les cellules sous forme textuelle, sans nettoyage métier ;
5. renseigne `source_file` et `source_row_number` ;
6. laisse PostgreSQL générer `loaded_at` ;
7. utilise une transaction, un verrou d'import et `ON CONFLICT DO NOTHING` ;
8. effectue un rollback automatique en cas d'erreur.

La commande affiche le nombre de lignes déjà présentes, nouvellement insérées et
présentes après import. Une première exécution sur une staging vide doit aboutir à
7 071 insertions ; une seconde doit aboutir à 0 insertion et 7 071 lignes présentes.
Ces résultats doivent être constatés sur PostgreSQL réel.

## Import du CSV préparé

Le fichier attendu est `data/processed/expenses_clean.csv` et doit contenir
exactement 7 070 lignes :

```bash
python -m database.load_data
```

L'import :

1. valide les colonnes, la cible et les 7 070 lignes ;
2. reconstruit `expense_date` depuis `annee`, `mois` et `jour` ;
3. crée les types et projets manquants ;
4. convertit `SANS_PROJET` en `project_id = NULL` ;
5. insère uniquement les dépenses absentes ;
6. exécute toutes les écritures dans une transaction ;
7. effectue un rollback automatique en cas d'erreur.

Un verrou transactionnel PostgreSQL empêche deux imports ExpenseAI simultanés. La
signature normalisée de chaque ligne permet de réexécuter le script sans créer de
doublons. Les lignes partageant le même `expense_group` restent bien des dépenses
distinctes lorsqu'une autre valeur métier diffère.

## Vérification des données

Dans `psql` :

```sql
SELECT source_file, COUNT(*) AS raw_rows
FROM staging_expenses_raw
GROUP BY source_file;

SELECT COUNT(*) AS expenses FROM expenses;

SELECT
    COUNT(*) FILTER (WHERE target = 0) AS approved,
    COUNT(*) FILTER (WHERE target = 1) AS refused
FROM expenses;

SELECT COUNT(*) AS projects_without_sentinel
FROM projects
WHERE code = 'SANS_PROJET';

SELECT COUNT(*) AS ml_rows FROM v_ml_expenses;
```

Pour une base initialement vide, les résultats attendus après import sont 7 070
dépenses, dont 6 956 approuvées et 114 refusées, et aucun projet `SANS_PROJET`.
Ces valeurs doivent être vérifiées sur PostgreSQL réel ; elles ne sont pas simulées
par la documentation.

## Benchmarks

Ouvrir `database/benchmark.sql`, remplacer
`REMPLACER_PAR_UN_GROUPE_EXISTANT` par une valeur retournée par la première requête,
puis exécuter :

```bash
psql -v ON_ERROR_STOP=1 -f database/benchmark.sql
```

Le script conserve la comparaison sur `expenses` avec les index temporairement
désactivés, puis avec le planificateur normal. Il ajoute des recherches
fonctionnellement comparables entre `staging_expenses_raw` et `expenses` sur le
groupe, la date, le montant et le type.

La staging répète les valeurs brutes en `TEXT`. La structure normalisée utilise des
types PostgreSQL adaptés, des référentiels et des index, ce qui réduit certaines
redondances et évite des conversions à la volée. Les requêtes ne sont toutefois pas
présentées comme strictement identiques : les schémas et les nombres de lignes
diffèrent. Les résultats à relever sont `Seq Scan`, `Index Scan` ou
`Bitmap Index Scan`, `Planning Time`, `Execution Time`, les lignes analysées ou
filtrées et les buffers. Aucun temps n'est inventé dans le dépôt.

## Sécurité et données réelles

- `.env` et les secrets ne doivent jamais être ajoutés à Git ;
- `data/raw/` et `data/processed/` sont ignorés par Git ;
- les sauvegardes PostgreSQL contenant des données réelles ne doivent pas être
  publiées ;
- la table staging et les noms de projets peuvent contenir des informations
  confidentielles et nécessitent des droits d'accès adaptés.
