-- Schéma PostgreSQL normalisé de ExpenseAI.
-- Le script est réexécutable : les tables et index existants sont conservés.

BEGIN;

CREATE TABLE IF NOT EXISTS expense_types (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS projects (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR NOT NULL UNIQUE,
    CONSTRAINT ck_projects_not_without_project CHECK (code <> 'SANS_PROJET')
);

CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    expense_group VARCHAR NOT NULL,
    expense_date DATE NOT NULL,
    expense_type_id BIGINT NOT NULL,
    amount_ttc NUMERIC(14, 2) NOT NULL,
    billable BOOLEAN NOT NULL,
    project_id BIGINT NULL,
    tax_rate NUMERIC(8, 4) NOT NULL,
    target SMALLINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_expenses_target CHECK (target IN (0, 1)),
    CONSTRAINT fk_expenses_expense_type
        FOREIGN KEY (expense_type_id)
        REFERENCES expense_types(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_expenses_project
        FOREIGN KEY (project_id)
        REFERENCES projects(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    expense_id BIGINT NULL,
    predicted_target SMALLINT NOT NULL,
    probability NUMERIC(6, 5) NOT NULL,
    model_version VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_predictions_target CHECK (predicted_target IN (0, 1)),
    CONSTRAINT ck_predictions_probability CHECK (
        probability >= 0 AND probability <= 1
    ),
    CONSTRAINT fk_predictions_expense
        FOREIGN KEY (expense_id)
        REFERENCES expenses(id)
        ON DELETE SET NULL
);

-- Zone brute volontairement séparée des tables utilisées par l'application.
-- Les valeurs métier restent en TEXT pour préserver la trace de l'export source.
CREATE TABLE IF NOT EXISTS staging_expenses_raw (
    id BIGSERIAL PRIMARY KEY,
    source_file VARCHAR NOT NULL,
    source_row_number BIGINT NOT NULL,
    expense_number TEXT,
    expense_date TEXT,
    expense_name TEXT,
    expense_type TEXT,
    amount_ttc_system_currency TEXT,
    billable TEXT,
    project_code TEXT,
    project_name TEXT,
    tax_rate TEXT,
    amount_ht_system_currency TEXT,
    status TEXT,
    receipt_filename TEXT,
    approval_date TEXT,
    rejection_reason TEXT,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_staging_source_row UNIQUE (source_file, source_row_number)
);

CREATE INDEX IF NOT EXISTS ix_expenses_expense_group
    ON expenses (expense_group);

CREATE INDEX IF NOT EXISTS ix_expenses_expense_date
    ON expenses (expense_date);

CREATE INDEX IF NOT EXISTS ix_expenses_expense_type_id
    ON expenses (expense_type_id);

CREATE INDEX IF NOT EXISTS ix_expenses_project_id
    ON expenses (project_id);

-- target ne reçoit pas d'index classique à ce stade : il ne possède que deux
-- modalités et la classe refusée est très minoritaire. Le choix devra être fondé
-- sur des requêtes réelles, leur sélectivité et EXPLAIN ANALYZE.

CREATE OR REPLACE VIEW v_ml_expenses AS
SELECT
    e.expense_group,
    et.name AS type,
    e.amount_ttc,
    e.billable,
    COALESCE(p.code, 'SANS_PROJET') AS project_code,
    e.tax_rate,
    EXTRACT(YEAR FROM e.expense_date)::SMALLINT AS annee,
    EXTRACT(MONTH FROM e.expense_date)::SMALLINT AS mois,
    EXTRACT(DAY FROM e.expense_date)::SMALLINT AS jour,
    (EXTRACT(ISODOW FROM e.expense_date)::SMALLINT - 1) AS jour_semaine,
    EXTRACT(QUARTER FROM e.expense_date)::SMALLINT AS trimestre,
    CASE
        WHEN EXTRACT(ISODOW FROM e.expense_date) IN (6, 7) THEN 1
        ELSE 0
    END::SMALLINT AS est_weekend,
    e.target
FROM expenses AS e
JOIN expense_types AS et ON et.id = e.expense_type_id
LEFT JOIN projects AS p ON p.id = e.project_id;

COMMENT ON TABLE staging_expenses_raw IS
    'Zone brute réservée à la traçabilité et aux benchmarks, non utilisée par Streamlit.';
COMMENT ON VIEW v_ml_expenses IS
    'Reconstruction lisible des variables préparées pour le futur Machine Learning.';

COMMIT;
