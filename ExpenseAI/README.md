# ExpenseAI

**Assistant intelligent pour l’analyse et la prédiction des notes de frais**

ExpenseAI est un projet réalisé dans le cadre d’un **Mastère Chef de projet Data
et Intelligence Artificielle**. Cette première version met en place une base
technique claire et évolutive, sans développer encore le modèle de Machine
Learning.

## Contexte et problématique

La validation manuelle des notes de frais peut être longue, hétérogène et difficile
à piloter lorsque les volumes augmentent. Les données historiques contiennent des
informations utiles pour analyser les décisions passées et assister les équipes
dans le traitement de nouvelles demandes.

L’enjeu de ExpenseAI est de transformer ces données en un outil d’aide à la
décision. À terme, un modèle supervisé estimera si une nouvelle note de frais est
susceptible d’être acceptée ou refusée. La décision finale restera interprétable et
placée sous contrôle humain.

## Objectifs

- Centraliser et structurer les données de notes de frais dans PostgreSQL.
- Auditer la qualité, la complétude et la conformité RGPD des données.
- Proposer des indicateurs et des visualisations interactives.
- Entraîner ultérieurement un modèle de classification supervisée.
- Expliquer les prédictions et conserver un historique des décisions.

## Fonctionnalités prévues

- Dashboard de suivi des notes de frais.
- Analyse exploratoire et contrôle de la qualité des données.
- Formulaire de prédiction pour une nouvelle dépense.
- Historique des prédictions et des décisions.
- Explicabilité du modèle, avec SHAP envisagé dans une phase ultérieure.

## Stack technique

- Python
- Streamlit
- PostgreSQL et SQLAlchemy
- pandas et NumPy
- Plotly
- scikit-learn et joblib pour la future phase Machine Learning
- openpyxl pour la lecture des fichiers Excel
- Git et GitHub

Le projet n’utilise pas Docker.

## Architecture

```text
ExpenseAI/
├── .streamlit/             # Configuration visuelle et serveur Streamlit
├── app/
│   ├── components/         # Composants visuels réutilisables
│   ├── pages/              # Pages de la navigation multipage
│   ├── utils/              # Utilitaires de l'interface
│   └── app.py              # Page d'accueil
├── data/
│   ├── raw/                # Données sources locales
│   └── processed/          # Données nettoyées et transformées
├── database/
│   ├── connection.py       # Connexion PostgreSQL par variables d'environnement
│   ├── schema.sql           # Tables, contraintes, vue et index PostgreSQL
│   ├── load_staging.py      # Import fidèle de l'Excel dans la staging
│   ├── load_data.py         # Import transactionnel du CSV préparé
│   ├── benchmark.sql        # Requêtes EXPLAIN ANALYZE
│   ├── models.py            # Modèles SQLAlchemy
│   └── README.md            # Guide PostgreSQL détaillé
├── ml/                     # Futurs modules de préparation, entraînement et prédiction
├── notebooks/              # Audit, EDA, prétraitement et modélisation
├── tests/                  # Tests automatisés
├── .env.example            # Modèle de configuration locale
├── requirements.txt        # Dépendances Python
└── streamlit_app.py        # Point d'entrée de l'application
```

## Installation

Prérequis : Python 3.10 ou version ultérieure et, pour les fonctions de persistance,
une instance PostgreSQL accessible.

Depuis le dossier `ExpenseAI`, créer puis activer un environnement virtuel :

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Sous Windows PowerShell, l’activation s’effectue avec :

```powershell
.venv\Scripts\Activate.ps1
```

Installer les dépendances :

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration PostgreSQL

Copier le modèle de configuration :

```bash
cp .env.example .env
```

Compléter ensuite `.env` sans jamais publier ce fichier :

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=expenseai
DB_USER=votre_utilisateur
DB_PASSWORD=votre_mot_de_passe
```

Une fois la base `expenseai` créée, le schéma peut être initialisé avec
`database/schema.sql`, puis l'Excel et le CSV préparé importés avec
`python -m database.load_staging` et `python -m database.load_data`. Les commandes
détaillées et les précautions sont documentées dans `database/README.md`.

PostgreSQL est la source principale du dashboard et de l'analyse exploratoire :
les données sont lues depuis `expenses`, `expense_types` et `projects`. La table
brute `staging_expenses_raw` n'est jamais utilisée par Streamlit.

## Lancement

```bash
streamlit run streamlit_app.py
```

Streamlit affiche ensuite l’adresse locale de l’application, habituellement
`http://localhost:8501`.

La page **Dashboard** propose des filtres combinables par période, statut, type,
projet et caractère facturable. Elle affiche les indicateurs et agrégats calculés
sur le périmètre filtré. Une connexion PostgreSQL valide dans `.env` est donc
nécessaire pour cette page.

## Tests

Les tests légers peuvent être exécutés sans PostgreSQL :

```bash
python -m unittest discover -s tests -v
```

## Données et confidentialité

Les vraies notes de frais peuvent contenir des données personnelles ou sensibles.
Le contenu des dossiers `data/raw` et `data/processed` est donc ignoré par Git par
défaut. Seuls des jeux d’exemple ou des données réellement anonymisées, portant le
suffixe `_example` ou `_anonymized`, doivent être ajoutés au dépôt après contrôle.

Ne placez jamais d’identifiants, de mots de passe ou de données personnelles dans
le code, les notebooks ou l’historique Git.

## État du projet

Cette version couvre l’architecture, l’audit, le preprocessing, la couche
PostgreSQL, l’analyse exploratoire et le dashboard interactif. Le Machine Learning et
les prédictions.
